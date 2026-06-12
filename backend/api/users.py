import logging
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from backend.core.database import get_db
from backend.core.config import get_settings
from backend.core.security import verify_password, get_password_hash, create_access_token, ALGORITHM
from backend.core.auth_provider import SupabaseAuthProvider
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
from pydantic import BaseModel, EmailStr
from typing import Optional, List

settings = get_settings()
logger = logging.getLogger(__name__)
supabase_auth_provider = SupabaseAuthProvider()

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
        # 1. Try internal JWT (signed with app_secret_key)
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
            # 2. Try Supabase JWT if internal fails
            if settings.supabase_jwt_secret:
                auth_payload = await supabase_auth_provider.verify_token(token)
                if auth_payload:
                    user_id = auth_payload.user_id
                    email = auth_payload.email
                    full_name = auth_payload.full_name

                    stmt = select(User).where(User.id == user_id)
                    result = await db.execute(stmt)
                    user = result.scalars().first()

                    if not user:
                        # Check if a user with this email already exists under a different login method
                        stmt_email = select(User).where(User.email == email)
                        res_email = await db.execute(stmt_email)
                        existing_user = res_email.scalars().first()
                        if existing_user:
                            logger.warning(f"OAuth email collision: user {email} already exists in database.")
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="An account with this email already exists. Please sign in using email and password."
                            )
                        
                        logger.info(f"Auto-provisioning new Supabase user: {email}")
                        try:
                            # Use a nested transaction (savepoint) to gracefully handle concurrent insertions
                            async with db.begin_nested():
                                user = User(
                                    id=user_id,
                                    email=email,
                                    hashed_password="SUPABASE_AUTH",
                                    full_name=full_name,
                                    is_active=True
                                )
                                db.add(user)
                                
                                workspace = Workspace(
                                    name=f"{user.full_name}'s Workspace",
                                    slug=f"ws-{user_id[:8]}"
                                )
                                db.add(workspace)
                                await db.flush()
                                
                                membership = WorkspaceMember(
                                    workspace_id=workspace.id,
                                    user_id=user.id,
                                    role=WorkspaceRole.OWNER
                                )
                                db.add(membership)
                            await db.commit()
                            await db.refresh(user)
                            logger.info(f"Successfully auto-provisioned user {user_id} and workspace")
                        except Exception as e:
                            # If duplicate key or unique violation, rollback savepoint and query again
                            await db.rollback()
                            logger.info(f"Collision or parallel auto-provisioning for {email}. Re-fetching user...")
                            stmt = select(User).where(User.id == user_id)
                            result = await db.execute(stmt)
                            user = result.scalars().first()
                            if not user:
                                logger.error(f"Failed to auto-provision user: {e}")
                                raise HTTPException(status_code=500, detail="User provisioning failed")

                    if user:
                        # Verify user has at least one workspace. 
                        # We use a sub-query check to avoid unnecessary flushes.
                        stmt_ws = select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
                        res_ws = await db.execute(stmt_ws)
                        if not res_ws.scalars().first():
                            logger.info(f"User {user.email} has no workspaces. Attempting to provision...")
                            try:
                                async with db.begin_nested():
                                    ws = Workspace(
                                        name=f"{user.full_name or email.split('@')[0]}'s Workspace",
                                        slug=f"ws-{user.id[:8]}-{secrets.token_hex(2)}"
                                    )
                                    db.add(ws)
                                    await db.flush()
                                    mem = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER)
                                    db.add(mem)
                                await db.commit()
                                await db.refresh(user)
                                logger.info(f"Late-provisioned workspace for {user.email}")
                            except Exception as ws_err:
                                await db.rollback()
                                logger.warning(f"Provisioning collision or error (likely handled by parallel request): {ws_err}")
                                # Re-fetch to see if it was created by a parallel request
                                res_retry = await db.execute(stmt_ws)
                                if not res_retry.scalars().first():
                                    logger.error("User still has no workspace after retry.")
                        return user

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
    
    auth_type = "oauth" if user.hashed_password == "SUPABASE_AUTH" else "password"
    return {"exists": True, "auth_type": auth_type}

