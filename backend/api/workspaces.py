import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import get_db
from backend.models.workspace import Workspace
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter(tags=["Workspaces"])
logger = logging.getLogger(__name__)


class WorkspaceCreate(BaseModel):
    name: str
    slug: str


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str


@router.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(request: WorkspaceCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new organization workspace.
    """
    result = await db.execute(select(Workspace).where(Workspace.slug == request.slug))
    existing = result.scalars().first()
    if existing:
        return WorkspaceResponse(
            id=existing.id,
            name=existing.name,
            slug=existing.slug
        )

    new_workspace = Workspace(name=request.name, slug=request.slug)
    db.add(new_workspace)
    await db.commit()
    await db.refresh(new_workspace)
    
    return WorkspaceResponse(
        id=new_workspace.id,
        name=new_workspace.name,
        slug=new_workspace.slug
    )
