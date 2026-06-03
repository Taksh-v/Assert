from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from backend.core.database import get_db
from backend.api.users import get_current_user
from backend.models.user import User
from backend.memory.episodic import EpisodicMemoryService

router = APIRouter(prefix="/memory", tags=["Memory"])

class EpisodeCreate(BaseModel):
    workspace_id: str
    title: str
    summary: str
    interaction: str
    outcome: str
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = {}

class EpisodeResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    summary: str
    created_at: str

@router.post("/episodes", response_model=Dict[str, Any])
async def create_episode(
    request: EpisodeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Record a new interaction episode."""
    service = EpisodicMemoryService(db)
    episode = await service.record_episode(
        workspace_id=request.workspace_id,
        user_id=current_user.id,
        title=request.title,
        summary=request.summary,
        interaction=request.interaction,
        outcome=request.outcome,
        tags=request.tags,
        metadata=request.metadata
    )
    return {"id": episode.id, "status": "recorded"}

@router.get("/episodes/search", response_model=List[Dict[str, Any]])
async def search_episodes(
    workspace_id: str,
    query: str,
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search for similar episodes in the current workspace."""
    service = EpisodicMemoryService(db)
    results = await service.query_similar(
        workspace_id=workspace_id,
        query=query,
        user_id=current_user.id,
        limit=limit
    )
    return results
