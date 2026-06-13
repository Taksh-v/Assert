import logging
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
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
    """
    token = None
    last_error = "None"
    
    # DEBUG: Print all headers to stdout (visible in HF logs)
    print("--- AUTH DEBUG START ---")
    x_auth = request.headers.get("x-user-authorization")
    std_auth = request.headers.get("authorization")
    
    print(f"DEBUG: x-user-authorization length: {len(x_auth) if x_auth else 0}")
    print(f"DEBUG: authorization length: {len(std_auth) if std_auth else 0}")
    
    # Safe debug: print first/last 2 chars of secret to verify it's loaded correctly
    sec = settings.supabase_jwt_secret
    if sec:
        print(f"DEBUG: Secret check: {sec[:2]}...{sec[-2:]} (len={len(sec)})")
    else:
        print("DEBUG: Secret is NONE")

    # 1. Extract token from multiple possible sources
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
        print(f"DEBUG: Token processing (len={len(token)})")
        print(f"DEBUG: Token start: {token[:10]}...")

        # 2. Try Supabase JWT verification
        if settings.supabase_jwt_secret:
            try:
                # DEBUG: Check what algorithm is actually being used
                header = jwt.get_unverified_header(token)
                print(f"DEBUG: Token header: {header}")
                
                # Loosen verification: strip secret and allow common algorithms
                payload = jwt.decode(
                    token, 
                    settings.supabase_jwt_secret.strip(), 
                    algorithms=["HS256", "RS256", "ES256"], 
                    options={"verify_aud": False}
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
                try:
                    h = jwt.get_unverified_header(token)
                    last_error = f"JWT Error: {str(e)} (Header: {h})"
                except:
                    last_error = f"JWT Error: {str(e)}"
                print(f"DEBUG: Supabase JWT Verification Failed: {last_error}")
                logger.error(f"AUTH_DIAGNOSTIC: Supabase JWT Verification Failed: {last_error}")
            except Exception as e:
                try:
                    h = jwt.get_unverified_header(token)
                    last_error = f"CORE_ERROR: {str(e)} (Header: {h})"
                except:
                    last_error = f"CORE_ERROR: {str(e)}"
                print(f"DEBUG: Fatal error during sync: {last_error}")
                logger.error(f"AUTH_DIAGNOSTIC: Fatal error during sync: {last_error}")
        else:
            last_error = "Secret not configured"
            print("ERROR: SUPABASE_JWT_SECRET NOT CONFIGURED")

        if user:
            if not user.is_active:
                raise HTTPException(status_code=403, detail="User account is deactivated")
            print(f"DEBUG: Auth Successful for {user.email}")
            print("--- AUTH DEBUG END ---")
            return user
    
    print("DEBUG: No valid user found after token processing")
    print("--- AUTH DEBUG END ---")
    
    # 3. Production logic: strict 401
    if not settings.is_development:
        # Versioning the message to confirm deployment
        detail = "Valid authentication token required [v5]"
        if not token:
            detail += " (Token not found)"
        else:
            detail += f" ({last_error})"
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Development-only fallback
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
