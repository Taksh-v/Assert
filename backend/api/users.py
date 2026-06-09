import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from backend.core.database import get_db
from backend.core.config import get_settings
from backend.core.security import verify_password, get_password_hash, create_access_token, ALGORITHM
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
from pydantic import BaseModel, EmailStr
from pydantic import BaseModel
from typing import Optional, List

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> User:
    x_user_auth = request.headers.get("x-user-authorization")
    if x_user_auth:
        if x_user_auth.lower().startswith("bearer "):
            token = x_user_auth[7:]
        else:
            token = x_user_auth

    if token:
        try:
            payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id:
                stmt = select(User).where(User.id == user_id)
                result = await db.execute(stmt)
                user = result.scalars().first()
                if user:
                    return user
        except JWTError:
            pass

    # In production, do not fall back. Force authenticated access.
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fallback to the first user in the database
    stmt = select(User).order_by(User.created_at.asc())
    result = await db.execute(stmt)
    user = result.scalars().first()
    if user:
        return user

    # Create a default user if database is clean
    new_user = User(
        email="default-user@example.com",
        hashed_password=get_password_hash("password"),
        full_name="Default User",
        is_active=True
    )
    db.add(new_user)
    await db.flush()
    
    # Also create the default workspace and add user as owner
    from backend.models.workspace import Workspace
    workspace = Workspace(name="Default Workspace", slug="default-workspace")
    db.add(workspace)
    await db.flush()
    
    membership = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=new_user.id,
        role=WorkspaceRole.OWNER
    )
    db.add(membership)
    await db.commit()
    await db.refresh(new_user)
    return new_user

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
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
