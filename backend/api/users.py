import logging
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import List, Optional
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

security = HTTPBearer(auto_error=False)

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: str
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Validate the Supabase JWT token and return the current user.
    Creates a shadow user in the local database if one doesn't exist.
    """
    token = None
    
    # 1. Extract token from multiple possible sources (robust extraction)
    # Order: x-user-authorization -> Authorization Header -> Query Param (fallback)
    
    x_auth = request.headers.get("x-user-authorization")
    std_auth = request.headers.get("authorization")
    
    # Use the first one that is actually present and not empty
    auth_header = x_auth if x_auth and len(x_auth) > 5 else std_auth
    
    if auth_header:
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
        else:
            token = auth_header
            
    if not token:
        token = request.query_params.get("access_token")

    if token:
        user = None
        logger.info(f"AUTH_DIAGNOSTIC: Processing token (len={len(token)})")

        # 2. Try Supabase JWT verification
        if settings.supabase_jwt_secret:
            try:
                # IMPORTANT: Supabase tokens must be verified with 'authenticated' audience
                payload = jwt.decode(
                    token, 
                    settings.supabase_jwt_secret, 
                    algorithms=["HS256"], 
                    audience="authenticated"
                )
                supabase_id: str = payload.get("sub")
                email: str = payload.get("email")

                if supabase_id and email:
                    # Check if user exists by supabase_id
                    stmt = select(User).where(User.supabase_id == supabase_id)
                    result = await db.execute(stmt)
                    user = result.scalars().first()

                    if not user:
                        logger.info(f"AUTH_DIAGNOSTIC: Syncing new Supabase user: {email}")
                        # Check for email collision
                        stmt = select(User).where(User.email == email)
                        result = await db.execute(stmt)
                        existing_email_user = result.scalars().first()

                        if existing_email_user:
                            existing_email_user.supabase_id = supabase_id
                            user = existing_email_user
                        else:
                            user = User(
                                email=email,
                                supabase_id=supabase_id,
                                hashed_password=None,
                                full_name=payload.get("user_metadata", {}).get("full_name") or email.split("@")[0]
                            )
                            db.add(user)
                        
                        await db.flush()
                        
                        # Ensure default workspace exists
                        stmt = select(Workspace).join(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
                        ws_result = await db.execute(stmt)
                        if not ws_result.scalars().first():
                            workspace_name = f"{user.full_name or email.split('@')[0]}'s Workspace"
                            slug = f"workspace-{user.id[:8]}"
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
                logger.error(f"AUTH_DIAGNOSTIC: Supabase JWT Verification Failed: {str(e)}")
            except Exception as e:
                logger.error(f"AUTH_DIAGNOSTIC: Database Error during Sync: {str(e)}")
                # Don't fail the whole app if sync has issues, try to continue
        else:
            logger.error("AUTH_DIAGNOSTIC: SUPABASE_JWT_SECRET NOT CONFIGURED")

        if user:
            if not user.is_active:
                raise HTTPException(status_code=403, detail="User account is deactivated")
            return user

    # 3. Production logic: strict 401
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Development-only fallback: Return the first user if it exists
    import os
    if os.environ.get("ASSEST_INSECURE_DEV_LOGIN") == "true":
        stmt = select(User).order_by(User.created_at.asc())
        result = await db.execute(stmt)
        user = result.scalars().first()
        if user:
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )

@router.get("/me", response_model=UserResponse)
@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
