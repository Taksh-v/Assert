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
    
    # DEBUG: Print all headers to stdout (visible in HF logs)
    print("--- AUTH DEBUG START ---")
    x_auth = request.headers.get("x-user-authorization")
    std_auth = request.headers.get("authorization")
    
    print(f"DEBUG: x-user-authorization length: {len(x_auth) if x_auth else 0}")
    print(f"DEBUG: authorization length: {len(std_auth) if std_auth else 0}")
    print(f"DEBUG: SUPABASE_JWT_SECRET configured: {bool(settings.supabase_jwt_secret)}")

    # 1. Extract token from multiple possible sources (robust extraction)
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
            print("DEBUG: Token found in query params")

    if token:
        user = None
        print(f"DEBUG: Token processing (len={len(token)})")

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
                print(f"DEBUG: Supabase JWT verified for {email}")

                if supabase_id and email:
                    # Check if user exists by supabase_id
                    stmt = select(User).where(User.supabase_id == supabase_id)
                    result = await db.execute(stmt)
                    user = result.scalars().first()

                    if not user:
                        print(f"DEBUG: User {email} not found locally, syncing...")
                        # Check for email collision
                        stmt = select(User).where(User.email == email)
                        result = await db.execute(stmt)
                        existing_email_user = result.scalars().first()

                        if existing_email_user:
                            print(f"DEBUG: Linking existing user {email} to Supabase ID")
                            existing_email_user.supabase_id = supabase_id
                            user = existing_email_user
                        else:
                            print(f"DEBUG: Creating brand new user: {email}")
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
                            print(f"DEBUG: Creating default workspace for {email}")
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
                        print(f"DEBUG: Sync complete for {email}")
            except JWTError as e:
                print(f"DEBUG: Supabase JWT Verification Failed: {str(e)}")
                logger.error(f"AUTH_DIAGNOSTIC: Supabase JWT Verification Failed: {str(e)}")
            except Exception as e:
                print(f"DEBUG: Database Error during Sync: {str(e)}")
                logger.error(f"AUTH_DIAGNOSTIC: Database Error during Sync: {str(e)}")
        else:
            print("ERROR: SUPABASE_JWT_SECRET NOT CONFIGURED")
            logger.error("AUTH_DIAGNOSTIC: SUPABASE_JWT_SECRET NOT CONFIGURED")

        if user:
            if not user.is_active:
                print(f"DEBUG: User {user.email} is deactivated")
                raise HTTPException(status_code=403, detail="User account is deactivated")
            print(f"DEBUG: Auth Successful for {user.email}")
            print("--- AUTH DEBUG END ---")
            return user
    
    print("DEBUG: No valid user found after token processing")
    print("--- AUTH DEBUG END ---")
    # 3. Production logic: strict 401
    if not settings.is_development:
        detail = "Valid authentication token required"
        if not token:
            detail += " (Token not found in headers)"
        elif not settings.supabase_jwt_secret:
            detail += " (Supabase secret not configured on backend)"
        elif not user:
            detail += " (Token verification failed or User not found locally)"
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
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
