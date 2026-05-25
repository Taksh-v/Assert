import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.generation.stream_generator import StreamGenerator

logger = logging.getLogger(__name__)

from backend.query.query_service import QueryService
from backend.api.users import get_current_user
from backend.models.user import User
from backend.core.database import get_db
from backend.api.connectors import verify_workspace_access
from backend.models.workspace import Workspace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(tags=["Query"])


class QueryRequest(BaseModel):
    question: str
    workspace_id: str
    conversation_id: Optional[str] = None
    response_format: str = "markdown"
    reasoning_mode: bool = False


class Source(BaseModel):
    title: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    query_id: str
    conversation_id: str


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Query the company knowledge base and persist the interaction.
    Tenant isolation is enforced by current_user's workspace access.
    """
    logger.info(f"Received query: {request.question} for workspace: {request.workspace_id}")
    
    # Enforce tenant isolation
    workspace_id = await verify_workspace_access(request.workspace_id, db, current_user)

    query_service = QueryService(db)
    
    try:
        result = await query_service.execute_query(
            question=request.question,
            workspace_id=workspace_id,
            user_id=current_user.id if current_user else None,
            conversation_id=request.conversation_id,
            reasoning_mode=request.reasoning_mode
        )

        return QueryResponse(
            answer=result["answer"],
            sources=[Source(**s) for s in result["sources"]],
            query_id=str(result["query_id"]),
            conversation_id=str(result["conversation_id"])
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/query/stream")
async def query_knowledge_base_stream(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stream the company knowledge base query using SSE.
    Tenant isolation is enforced by current_user's workspace access.
    """
    logger.info(f"Received streaming query: {request.question} for workspace: {request.workspace_id}")
    workspace_id = await verify_workspace_access(request.workspace_id, db, current_user)
    
    query_service = QueryService(db)

    return StreamingResponse(
        query_service.stream_query(
            question=request.question,
            workspace_id=workspace_id,
            user_id=current_user.id if current_user else None,
            conversation_id=request.conversation_id,
            reasoning_mode=request.reasoning_mode
        ),
        media_type="text/event-stream"
    )


