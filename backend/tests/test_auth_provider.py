import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, Request
from jose import jwt, JWTError
from backend.api.users import get_current_user, get_jwks
from backend.models.user import User

@pytest.mark.asyncio
@patch("jose.jwt.decode")
async def test_get_current_user_valid_hs256_token(mock_jwt_decode):
    mock_jwt_decode.return_value = {
        "sub": "user-hs256-123",
        "email": "hs256@example.com",
        "role": "authenticated"
    }
    
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"x-user-authorization": "Bearer valid-hs256-token"}
    mock_request.query_params = {}
    
    db = AsyncMock()
    mock_user = User(id="u-hs256", email="hs256@example.com", supabase_id="user-hs256-123", is_active=True)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_user
    db.execute.return_value = mock_result
    
    with patch("backend.api.users.settings") as mock_settings:
        mock_settings.supabase_jwt_secret = "test-secret"
        mock_settings.is_development = False
        
        with patch("jose.jwt.get_unverified_header") as mock_header, \
             patch("jose.jwt.get_unverified_claims") as mock_claims:
            
            mock_header.return_value = {"alg": "HS256"}
            mock_claims.return_value = {}
            
            user = await get_current_user(mock_request, db=db)
            
            assert user.email == "hs256@example.com"
            assert user.id == "u-hs256"

@pytest.mark.asyncio
@patch("backend.api.users.get_jwks")
@patch("jose.jwt.decode")
async def test_get_current_user_valid_es256_token(mock_jwt_decode, mock_get_jwks):
    mock_get_jwks.return_value = {"keys": [{"kid": "test-kid"}]}
    mock_jwt_decode.return_value = {
        "sub": "user-es256-123",
        "email": "es256@example.com",
        "role": "authenticated",
        "iss": "https://mayvqbzbuqhvmjxyvdib.supabase.co/auth/v1"
    }
    
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"x-user-authorization": "Bearer valid-es256-token"}
    mock_request.query_params = {}
    
    db = AsyncMock()
    mock_user = User(id="u-es256", email="es256@example.com", supabase_id="user-es256-123", is_active=True)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_user
    db.execute.return_value = mock_result
    
    with patch("backend.api.users.settings") as mock_settings:
        mock_settings.supabase_url = "https://mayvqbzbuqhvmjxyvdib.supabase.co"
        mock_settings.supabase_anon_key = "test-anon-key"
        mock_settings.is_development = False
        
        with patch("jose.jwt.get_unverified_header") as mock_header, \
             patch("jose.jwt.get_unverified_claims") as mock_claims:
            
            mock_header.return_value = {"alg": "ES256"}
            mock_claims.return_value = {"iss": "https://mayvqbzbuqhvmjxyvdib.supabase.co/auth/v1"}
            
            user = await get_current_user(mock_request, db=db)
            
            assert user.email == "es256@example.com"
            assert user.supabase_id == "user-es256-123"

@pytest.mark.asyncio
@patch("jose.jwt.decode")
async def test_get_current_user_auto_provision(mock_jwt_decode):
    mock_jwt_decode.return_value = {
        "sub": "user-new-123",
        "email": "newuser@example.com",
        "role": "authenticated",
        "user_metadata": {
            "full_name": "New User"
        }
      }
      
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"x-user-authorization": "Bearer valid-token"}
    mock_request.query_params = {}
    
    db = AsyncMock()
    
    async def mock_flush():
        for call in db.add.call_args_list:
            obj = call[0][0]
            if getattr(obj, "id", None) is None:
                obj.id = "mock-uuid-12345678"
            if hasattr(obj, "is_active") and getattr(obj, "is_active") is None:
                obj.is_active = True
    db.flush.side_effect = mock_flush
    
    mock_result_empty = MagicMock()
    mock_result_empty.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_result_empty
    
    with patch("backend.api.users.settings") as mock_settings:
        mock_settings.supabase_jwt_secret = "test-secret"
        mock_settings.is_development = False
        
        with patch("jose.jwt.get_unverified_header") as mock_header, \
             patch("jose.jwt.get_unverified_claims") as mock_claims:
            
            mock_header.return_value = {"alg": "HS256"}
            mock_claims.return_value = {}
            
            user = await get_current_user(mock_request, db=db)
            
            assert user.email == "newuser@example.com"
            assert user.full_name == "New User"
            assert user.supabase_id == "user-new-123"
            db.add.assert_any_call(user)

@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"x-user-authorization": "Bearer invalid-token-signature"}
    mock_request.query_params = {}
    
    db = AsyncMock()
    
    with patch("backend.api.users.settings") as mock_settings:
        mock_settings.supabase_jwt_secret = "test-secret"
        mock_settings.is_development = False
        
        with patch("jose.jwt.get_unverified_header") as mock_header:
            mock_header.side_effect = JWTError("Invalid token format")
            
            with pytest.raises(HTTPException) as excinfo:
                await get_current_user(mock_request, db=db)
            assert excinfo.value.status_code == 401
