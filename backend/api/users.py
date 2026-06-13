import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from jose import jwt, JWTError
from datetime import datetime

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
    Validate the Supabase JWT token and return the current user.
    Uses multi-layered token extraction and explicitly ignores non-Supabase tokens.
    """
    token = None
    last_error = "None"
    
    # 1. Multi-layered token extraction (Robustness Priority)
    # Order: Custom Header -> Query Param -> x-user-authorization -> Authorization Header
    
    # Try custom header (least likely to be stripped or overwritten)
    token = request.headers.get("x-supabase-auth")
    
    if not token:
        # Try custom query param from proxy
        token = request.query_params.get("supabase_token")
        
    if not token:
        # Try proxy-specific header
        x_auth = request.headers.get("x-user-authorization")
        if x_auth:
            token = x_auth[7:] if x_auth.lower().startswith("bearer ") else x_auth
            
    if not token:
        # Standard header
        std_auth = request.headers.get("authorization")
        if std_auth:
            token = std_auth[7:] if std_auth.lower().startswith("bearer ") else std_auth

    # 2. Process Token
    if token:
        user = None
        
        # Detect token type before decoding
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
            # Hugging Face internal tokens use ES256 - we MUST ignore them
            if alg == "ES256":
                token = None # Discard and stop processing
                last_error = "Hugging Face system token ignored (ES256)"
        except Exception as e:
            pass # Not a valid JWT or header unreadable

        # 3. Verify with Supabase Secret
        if token and settings.supabase_jwt_secret:
            try:
                # Decrypt using strict HS256 (industry standard for Supabase symmetric keys)
                payload = jwt.decode(
                    token, 
                    settings.supabase_jwt_secret.strip(), 
                    algorithms=["HS256"], 
                    audience="authenticated"
                )
                supabase_id: str = payload.get("sub")
                email: str = payload.get("email")

                if supabase_id and email:
                    # DB Sync logic
                    stmt = select(User).where(User.supabase_id == supabase_id)
                    result = await db.execute(stmt)
                    user = result.scalars().first()

                    if not user:
                        # User found in Supabase but not yet in local database
                        stmt = select(User).where(User.email == email)
                        result = await db.execute(stmt)
                        existing_user = result.scalars().first()

                        if existing_user:
                            # Link existing account
                            existing_user.supabase_id = supabase_id
                            user = existing_user
                        else:
                            # Create brand new record
                            user = User(
                                email=email,
                                supabase_id=supabase_id,
                                hashed_password=None,
                                full_name=payload.get("user_metadata", {}).get("full_name") or email.split("@")[0]
                            )
                            db.add(user)
                        
                        await db.flush()
                        
                        # Verify workspace existence
                        stmt = select(Workspace).join(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
                        ws_result = await db.execute(stmt)
                        if not ws_result.scalars().first():
                            workspace_name = f"{user.full_name or email.split('@')[0]}'s Workspace"
                            slug = f"workspace-{user.id[:8]}-{secrets.token_hex(4)}"
                            new_workspace = Workspace(name=workspace_name, slug=slug)
                            db.add(new_workspace)
                            await db.flush()

                            membership = WorkspaceMember(
                                workspace_id=new_workspace.id,
                                user_id=user.id,
                                role=WorkspaceRole.OWNER
                            )
                            db.add(membership)
                            
                        await db.commit()
                        await db.refresh(user)
            except JWTError as e:
                last_error = f"JWT Validation Failed: {str(e)}"
            except Exception as e:
                last_error = f"Sync Failure: {str(e)}"
                logger.error(f"Persistence error: {e}")

        if user:
            if not user.is_active:
                raise HTTPException(status_code=403, detail="Account disabled")
            return user

    # 4. Final failure response
    if not settings.is_development:
        detail = "Authentication failed"
        if not token:
            detail = f"Authentication required ({last_error})"
        else:
            detail = f"Invalid session ({last_error})"
            
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Insecure Dev Login (Only if environment variable is TRUE)
    if os.environ.get("ASSEST_INSECURE_DEV_LOGIN") == "true":
        stmt = select(User).order_by(User.created_at.asc())
        result = await db.execute(stmt)
        user = result.scalars().first()
        if user:
            return user

    raise HTTPException(status_code=401, detail="Authentication required")

import os
import secrets

@router.get("/me", response_model=UserResponse)
@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/check-email")
async def check_email(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        return {"exists": False, "auth_type": "none"}
    
    return {"exists": True, "auth_type": "password"}
