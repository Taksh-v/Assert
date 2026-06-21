import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.core.database import get_db
from backend.models.conversation import Conversation
from backend.models.query_log import QueryLog
from backend.models.workspace import Workspace
from pydantic import BaseModel
from datetime import datetime
from backend.api.users import get_current_user
from backend.models.user import User
from backend.api.connectors import verify_workspace_access

router = APIRouter(prefix="/conversations", tags=["Conversations"])
logger = logging.getLogger(__name__)


async def resolve_workspace_id(db: AsyncSession, workspace_ref: str) -> str:
    stmt = select(Workspace).where(
        (Workspace.id == workspace_ref) | (Workspace.slug == workspace_ref)
    )
    result = await db.execute(stmt)
    workspace = result.scalars().first()
    if workspace:
        return workspace.id
    if workspace_ref == "default-workspace":
        workspace = Workspace(name="Default Workspace", slug="default-workspace")
        db.add(workspace)
        await db.commit()
        return workspace.id
    raise HTTPException(status_code=404, detail="Workspace not found")


class MessageResponse(BaseModel):
    id: str
    question: str
    answer: Optional[str]
    sources: List[dict]
    created_at: datetime
    faithfulness_score: Optional[float] = None
    relevance_score: Optional[float] = None
    eval_reasoning: Optional[str] = None
    response_time_ms: Optional[int] = None



class ConversationResponse(BaseModel):
    id: str
    title: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse]


class ConversationCreate(BaseModel):
    workspace_id: str
    title: Optional[str] = "New Conversation"


@router.get("", response_model=List[ConversationResponse])
async def list_conversations(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all conversations for a workspace."""
    resolved_workspace_id = await verify_workspace_access(workspace_id, db, current_user)
    stmt = select(Conversation).where(Conversation.workspace_id == resolved_workspace_id).order_by(desc(Conversation.updated_at))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new conversation thread."""
    workspace_id = await verify_workspace_access(request.workspace_id, db, current_user)
    new_conv = Conversation(
        workspace_id=workspace_id,
        title=request.title
    )
    db.add(new_conv)
    await db.commit()
    await db.refresh(new_conv)
    return new_conv


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get conversation details and messages."""
    from sqlalchemy.orm import selectinload
    stmt = select(Conversation).options(selectinload(Conversation.messages)).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    await verify_workspace_access(conversation.workspace_id, db, current_user)
    return conversation


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a conversation thread."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    await verify_workspace_access(conversation.workspace_id, db, current_user)
    await db.delete(conversation)
    await db.commit()
    return {"status": "success"}
