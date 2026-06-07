import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import get_db
from backend.models.workspace import Workspace
from pydantic import BaseModel
from sqlalchemy import select

from backend.api.users import get_current_user
from backend.models.user import User
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole

router = APIRouter(tags=["Workspaces"])
logger = logging.getLogger(__name__)


class WorkspaceCreate(BaseModel):
    name: str
    slug: str


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    role: Optional[str] = None


@router.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(
    request: WorkspaceCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new organization workspace.
    """
    result = await db.execute(select(Workspace).where(Workspace.slug == request.slug))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Workspace slug already exists")

    new_workspace = Workspace(name=request.name, slug=request.slug)
    db.add(new_workspace)
    await db.flush()
    
    # Add creator as owner
    membership = WorkspaceMember(
        workspace_id=new_workspace.id,
        user_id=current_user.id,
        role=WorkspaceRole.OWNER
    )
    db.add(membership)
    await db.commit()
    await db.refresh(new_workspace)
    
    return WorkspaceResponse(
        id=new_workspace.id,
        name=new_workspace.name,
        slug=new_workspace.slug,
        role=WorkspaceRole.OWNER
    )


@router.get("/workspaces", response_model=List[WorkspaceResponse])
async def list_my_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all workspaces the current user belongs to.
    """
    stmt = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            role=role
        )
        for workspace, role in rows
    ]
