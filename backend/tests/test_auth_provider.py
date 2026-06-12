import pytest
import time
from datetime import datetime, timedelta
from jose import jwt
from backend.core.auth_provider import SupabaseAuthProvider, UserAuthPayload
from backend.core.config import get_settings

settings = get_settings()
SECRET = "test-secret-key-123-abc-for-jwt-testing-only-12345"

@pytest.fixture
def auth_provider():
    return SupabaseAuthProvider(jwt_secret=SECRET)

@pytest.mark.asyncio
async def test_supabase_auth_provider_valid_token(auth_provider):
    payload = {
        "sub": "user-12345",
        "email": "user@example.com",
        "role": "authenticated",
        "user_metadata": {
            "full_name": "Test User"
        },
        "exp": int(time.time() + 3600)
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    res = await auth_provider.verify_token(token)
    
    assert res is not None
    assert res.user_id == "user-12345"
    assert res.email == "user@example.com"
    assert res.full_name == "Test User"

@pytest.mark.asyncio
async def test_supabase_auth_provider_invalid_signature(auth_provider):
    payload = {
        "sub": "user-12345",
        "email": "user@example.com",
        "role": "authenticated"
    }
    token = jwt.encode(payload, "wrong-secret-key-456", algorithm="HS256")
    res = await auth_provider.verify_token(token)
    assert res is None

@pytest.mark.asyncio
async def test_supabase_auth_provider_invalid_role(auth_provider):
    payload = {
        "sub": "user-12345",
        "email": "user@example.com",
        "role": "anonymous"
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    res = await auth_provider.verify_token(token)
    assert res is None

@pytest.mark.asyncio
async def test_supabase_auth_provider_expired_token(auth_provider):
    payload = {
        "sub": "user-12345",
        "email": "user@example.com",
        "role": "authenticated",
        "exp": int(time.time() - 3600)
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    res = await auth_provider.verify_token(token)
    assert res is None

@pytest.mark.asyncio
async def test_supabase_auth_provider_missing_fields(auth_provider):
    payload = {
        "sub": "user-12345",
        # missing email
        "role": "authenticated"
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    res = await auth_provider.verify_token(token)
    assert res is None
