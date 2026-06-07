import logging
from datetime import datetime
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.generation.stream_generator import StreamGenerator

logger = logging.getLogger(__name__)

from backend.observability.telemetry import tracer

from backend.query.query_service import QueryService
from backend.api.users import get_current_user
from backend.models.user import User
from backend.core.database import get_db, async_session
from backend.api.connectors import verify_workspace_access
from backend.models.workspace import Workspace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(tags=["Query"])

import sys
# Rate limiting — import the limiter from the main app module
from slowapi import Limiter
from slowapi.util import get_remote_address

# Disable rate limiting during tests to avoid request injection errors in direct endpoint unit tests
_limiter = Limiter(key_func=get_remote_address, enabled="pytest" not in sys.modules)


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
@_limiter.limit("10/minute")
async def query_knowledge_base(
    request: Request,
    query_req: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
):
    """
    Query the company knowledge base and persist the interaction.
    Tenant isolation is enforced by current_user's workspace access.
    """
    logger.info(f"Received query: {query_req.question} for workspace: {query_req.workspace_id}")
    request_id = x_request_id or str(uuid.uuid4())
    
    # Enforce tenant isolation
    workspace_id = await verify_workspace_access(query_req.workspace_id, db, current_user)

    query_service = QueryService(db)
    
    with tracer.start_as_current_span("api.query") as span:
        span.set_attribute("request_id", request_id)
        span.set_attribute("workspace_id", workspace_id)
        span.set_attribute("question", query_req.question[:500])
        try:
            result = await query_service.execute_query(
                question=query_req.question,
                workspace_id=workspace_id,
                user_id=current_user.id if current_user else None,
                conversation_id=query_req.conversation_id,
                reasoning_mode=query_req.reasoning_mode,
                request_id=request_id,
            )

            return QueryResponse(
                answer=result["answer"],
                sources=[Source(**s) for s in result["sources"]],
                query_id=str(result["query_id"]),
                conversation_id=str(result["conversation_id"])
            )
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            span.record_exception(e)
            raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/query/stream")
@_limiter.limit("10/minute")
async def query_knowledge_base_stream(
    request: Request,
    query_req: QueryRequest,
    current_user: User = Depends(get_current_user),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
):
    """
    Stream the company knowledge base query using SSE.
    Tenant isolation is enforced by current_user's workspace access.
    """
    logger.info(f"Received streaming query: {query_req.question} for workspace: {query_req.workspace_id}")
    request_id = x_request_id or str(uuid.uuid4())
    
    async with async_session() as db:
        workspace_id = await verify_workspace_access(query_req.workspace_id, db, current_user)
    
    query_service = QueryService(None)

    # Note: The actual span is managed inside the AsyncGenerator within stream_query
    return StreamingResponse(
        query_service.stream_query(
            question=query_req.question,
            workspace_id=workspace_id,
            user_id=current_user.id if current_user else None,
            conversation_id=query_req.conversation_id,
            reasoning_mode=query_req.reasoning_mode,
            request_id=request_id,
        ),
        media_type="text/event-stream"
    )


