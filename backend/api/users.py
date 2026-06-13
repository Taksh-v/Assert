import logging
import os
import secrets
import asyncio
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from jose import jwt, JWTError
from datetime import datetime

_jwks_cache = None
_jwks_lock = asyncio.Lock()

async def get_jwks(supabase_url: str, supabase_anon_key: str) -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    async with _jwks_lock:
        if _jwks_cache is not None:
            return _jwks_cache
        jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        headers = {"apikey": supabase_anon_key}
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(jwks_url, headers=headers)
            res.raise_for_status()
            _jwks_cache = res.json()
            return _jwks_cache

from backend.core.database import get_db
from backend.core.config import get_settings
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole

router = APIRouter(tags=["Users"])
settings = get_settings()
logger = logging.getLogger(__name__)

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserResponse(UserBase):
    id: str
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    ULTRA-ROBUST TOKEN FINDER
    Iterates through all candidates and logs precisely what is happening.
    """
    
    candidates = []
    # 1. Custom Headers
    for h in ["x-supabase-token", "x-access-token", "token", "x-user-authorization"]:
        val = request.headers.get(h)
        if val: candidates.append(("Header " + h, val))
        
    # 2. Query Params
    for p in ["supabase_token", "access_token"]:
        val = request.query_params.get(p)
        if val: candidates.append(("Query " + p, val))
        
    # 3. Standard Auth
    std_auth = request.headers.get("authorization")
    if std_auth:
        candidates.append(("Standard Auth", std_auth))

    best_error = "No tokens provided"
    
    for label, raw_val in candidates:
        if not raw_val or len(raw_val) < 10: continue
        
        # Strip bearer
        token = raw_val[7:] if raw_val.lower().startswith("bearer ") else raw_val
        
        # Skip Hugging Face system platform tokens (they are not user JWTs)
        if token.startswith("hf_"):
            logger.debug("Skipping Hugging Face system token in %s", label)
            continue
            
        try:
            # PRE-CHECK: Algorithm
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
            print(f"DEBUG: Checking {label} (start: {token[:10]}..., alg: {alg})")
            
            # Skip check if algorithm is not supported
            if alg not in ("HS256", "RS256", "ES256"):
                best_error = f"Unsupported token algorithm {alg} on {label}"
                continue

            # Check unverified claims for issuer to filter system platform pings
            claims = jwt.get_unverified_claims(token)
            iss = claims.get("iss", "")
            if alg in ("RS256", "ES256"):
                if "supabase" not in iss:
                    best_error = f"Ignored non-Supabase asymmetric token from {label}"
                    continue

            # DECODE: Supabase
            if alg == "HS256":
                if not settings.supabase_jwt_secret:
                    best_error = "Secret missing on backend"
                    break
                key = settings.supabase_jwt_secret.strip()
                algorithms = ["HS256"]
            else: # RS256, ES256
                if not settings.supabase_url or not settings.supabase_anon_key:
                    best_error = "Supabase URL/Anon key missing on backend for asymmetric verification"
                    continue
                key = await get_jwks(settings.supabase_url, settings.supabase_anon_key)
                algorithms = ["RS256", "ES256"]

            payload = jwt.decode(
                token, 
                key, 
                algorithms=algorithms, 
                audience="authenticated"
            )
            
            supabase_id = payload.get("sub")
            email = payload.get("email")
            
            if supabase_id and email:
                # FOUND IT! Sync user
                stmt = select(User).where(User.supabase_id == supabase_id)
                result = await db.execute(stmt)
                user = result.scalars().first()

                if not user:
                    stmt = select(User).where(User.email == email)
                    result = await db.execute(stmt)
                    user = result.scalars().first()
                    if user: user.supabase_id = supabase_id
                    else:
                        user = User(
                            email=email,
                            supabase_id=supabase_id,
                            hashed_password=None,
                            full_name=payload.get("user_metadata", {}).get("full_name") or email.split("@")[0]
                        )
                        db.add(user)
                    
                    await db.flush()
                    
                    # Workspace Check
                    stmt = select(Workspace).join(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
                    ws_result = await db.execute(stmt)
                    if not ws_result.scalars().first():
                        workspace_name = f"{user.full_name or email.split('@')[0]}'s Workspace"
                        slug = f"workspace-{user.id[:8]}-{secrets.token_hex(4)}"
                        new_workspace = Workspace(name=workspace_name, slug=slug)
                        db.add(new_workspace)
                        await db.flush()
                        db.add(WorkspaceMember(workspace_id=new_workspace.id, user_id=user.id, role=WorkspaceRole.OWNER))
                        
                    await db.commit()
                    await db.refresh(user)
                
                if user.is_active: return user
                else: raise HTTPException(status_code=403, detail="Account disabled")
                    
        except JWTError as e:
            best_error = f"JWT Invalid on {label}: {str(e)}"
        except Exception as e:
            best_error = f"Sync Error on {label}: {str(e)}"

    # 4. Fail
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication required ({best_error})",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Insecure Dev Fallback
    if os.environ.get("ASSEST_INSECURE_DEV_LOGIN") == "true":
        stmt = select(User).order_by(User.created_at.asc()); result = await db.execute(stmt)
        user = result.scalars().first()
        if user: return user

    raise HTTPException(status_code=401, detail="Authentication required")

@router.get("/me", response_model=UserResponse)
@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/check-email")
async def check_email(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    email = data.get("email")
    if not email: raise HTTPException(status_code=400, detail="Email is required")
    stmt = select(User).where(User.email == email); result = await db.execute(stmt)
    user = result.scalars().first()
    return {"exists": bool(user), "auth_type": "password" if user else "none"}
