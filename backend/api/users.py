import logging
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from jose import jwt, JWTError
from datetime import datetime

from backend.core.database import get_db
from backend.core.config import get_settings
from backend.core.security import verify_password, get_password_hash, create_access_token, ALGORITHM
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole

router = APIRouter(tags=["Users"])
settings = get_settings()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False)

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
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Validate the authentication token and return the current user.
    Supports only internal JWTs signed with app_secret_key.
    """
    # 1. Resolve token from header if oauth2_scheme didn't find it (common with custom proxies)
    if not token:
        x_user_auth = request.headers.get("x-user-authorization") or request.headers.get("authorization")
        if x_user_auth:
            if x_user_auth.lower().startswith("bearer "):
                token = x_user_auth[7:]
            else:
                token = x_user_auth

    if token:
        # Try internal JWT (signed with app_secret_key)
        try:
            payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id:
                stmt = select(User).where(User.id == user_id)
                result = await db.execute(stmt)
                user = result.scalars().first()
                if user:
                    if not user.is_active:
                        raise HTTPException(status_code=403, detail="User account is deactivated")
                    return user
        except JWTError:
            pass

    # Production logic: strict 401
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
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

@router.post("/signup", response_model=UserResponse)
@router.post("/register", response_model=UserResponse)
async def signup(request: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user and create their initial personal workspace.
    """
    # Check if user exists
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    new_user = User(
        email=request.email,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name
    )
    db.add(new_user)
    await db.flush()
    
    # Create personal workspace
    workspace_name = f"{request.full_name or request.email.split('@')[0]}'s Workspace"
    slug = f"workspace-{new_user.id[:8]}"
    new_workspace = Workspace(name=workspace_name, slug=slug)
    db.add(new_workspace)
    await db.flush()
    
    # Add user as OWNER of the workspace
    membership = WorkspaceMember(
        workspace_id=new_workspace.id,
        user_id=new_user.id,
        role=WorkspaceRole.OWNER
    )
    db.add(membership)
    
    await db.commit()
    await db.refresh(new_user)
    
    return new_user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    Authenticate user and return JWT token.
    """
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account does not exist. Please create an account."
        )
    
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


class EmailCheckRequest(BaseModel):
    email: str

class EmailCheckResponse(BaseModel):
    exists: bool
    auth_type: str

@router.post("/users/check-email", response_model=EmailCheckResponse)
async def check_email(request: EmailCheckRequest, db: AsyncSession = Depends(get_db)):
    """
    Check if a user exists with the given email, and return their auth type.
    """
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        return {"exists": False, "auth_type": "none"}
    
    return {"exists": True, "auth_type": "password"}
