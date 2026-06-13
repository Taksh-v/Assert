import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from jose import jwt, JWTError

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
    Creates a shadow user in the local database if one doesn't exist.
    
    Data is persisted via the DATABASE_URL (SQLite or PostgreSQL).
    """
    token = None
    
    # 1. Extract token from multiple possible sources
    # Priority: Query Param -> Proxy Header -> Standard Header
    token = request.query_params.get("supabase_token")
    
    if not token:
        # Check both custom proxy and standard headers
        auth_header = request.headers.get("x-user-authorization") or request.headers.get("authorization")
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:]
            else:
                token = auth_header
            
    if not token:
        # Fallback to access_token query param
        token = request.query_params.get("access_token")

    if token:
        user = None
        if settings.supabase_jwt_secret:
            try:
                # Decrypt Supabase token
                payload = jwt.decode(
                    token, 
                    settings.supabase_jwt_secret.strip(), 
                    algorithms=["HS256"], 
                    audience="authenticated"
                )
                supabase_id: str = payload.get("sub")
                email: str = payload.get("email")

                if supabase_id and email:
                    # Sync logic
                    stmt = select(User).where(User.supabase_id == supabase_id)
                    result = await db.execute(stmt)
                    user = result.scalars().first()

                    if not user:
                        # User exists in Supabase but not in local persistence yet
                        # Check for existing email to link accounts
                        stmt = select(User).where(User.email == email)
                        result = await db.execute(stmt)
                        existing_user = result.scalars().first()

                        if existing_user:
                            existing_user.supabase_id = supabase_id
                            user = existing_user
                        else:
                            # Create new user record
                            user = User(
                                email=email,
                                supabase_id=supabase_id,
                                hashed_password=None,
                                full_name=payload.get("user_metadata", {}).get("full_name") or email.split("@")[0]
                            )
                            db.add(user)
                        
                        await db.flush()
                        
                        # Ensure user has at least one workspace
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
            except JWTError:
                # Token verification failed
                pass
            except Exception as e:
                logger.error(f"Error during User persistence sync: {e}")

        if user:
            if not user.is_active:
                raise HTTPException(status_code=403, detail="User account is deactivated")
            return user

    # Strict production auth
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Dev fallback
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

import os

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
