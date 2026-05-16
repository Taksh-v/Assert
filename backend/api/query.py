import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from backend.query.retriever import Retriever
from backend.query.generator import Generator
try:
    from backend.agent.query_orchestrator import run_multi_agent_query
except ImportError:
    logger.warning("Query orchestrator dependencies missing. Falling back to standard mode.")
    run_multi_agent_query = None
from backend.core.database import get_db
from backend.models.query_log import QueryLog
from backend.models.conversation import Conversation
from backend.models.knowledge_gap import KnowledgeGap
from backend.models.workspace import Workspace
from backend.core.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

router = APIRouter(tags=["Query"])


async def resolve_workspace_id(db: AsyncSession, workspace_ref: str) -> str:
    """Accept either a workspace UUID/id or a slug; create the default dev workspace if needed."""
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
        await db.flush()
        return workspace.id

    raise HTTPException(status_code=404, detail="Workspace not found")


class QueryRequest(BaseModel):
    question: str
    workspace_id: str
    conversation_id: Optional[str] = None
    response_format: str = "markdown"


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
    x_api_key: str = Header(..., description="API Key for authentication")
):
    """
    Query the company knowledge base and persist the interaction.
    """
    logger.info(f"Received query: {request.question} for workspace: {request.workspace_id}")
    
    if x_api_key != "assest_secret_key":
        raise HTTPException(status_code=401, detail="Invalid API Key")

    workspace_id = await resolve_workspace_id(db, request.workspace_id)

    # 1. Handle Conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        # Create a new conversation if not provided
        new_conv = Conversation(
            workspace_id=workspace_id,
            title=request.question[:50] + "..." if len(request.question) > 50 else request.question
        )
        db.add(new_conv)
        await db.commit()
        await db.refresh(new_conv)
        conversation_id = new_conv.id
    
    settings = get_settings()
    
    try:
        using_multi_agent = settings.enable_multi_agent and run_multi_agent_query is not None
        
        if using_multi_agent:
            # Use the new multi-agent orchestration system
            from datetime import datetime
            start_time = datetime.utcnow()
            
            agent_result = await run_multi_agent_query(
                question=request.question,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                max_iterations=2
            )
            
            answer_text = agent_result["answer"]
            sources = [Source(title=s.get("title", "Unknown"), url=s.get("url", "")) 
                      for s in agent_result["sources"]]
            confidence = agent_result["confidence"]
            
            # Log multi-agent metadata
            metadata = {
                "iterations": agent_result["iterations"],
                "verification_results": agent_result["verification_results"],
                "critique": agent_result["critique"],
                "confidence": confidence,
                "processing_time_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000)
            }
            
        else:
            # Fallback to legacy single-pass retrieval
            retriever = Retriever()
            generator = Generator()
            
            chunks = await retriever.search(request.question, workspace_id)
            max_score = max([c.score for c in chunks]) if chunks else 0.0
            
            # Log metadata
            metadata = {
                "retrieved_chunks": len(chunks),
                "max_score": max_score,
                "method": "legacy"
            }
        
        # 2b. Knowledge Gap Tracking (Assest Architecture Property 5)
        if (using_multi_agent and confidence < 0.6) or \
           (not using_multi_agent and (not chunks or max_score < 0.4)):
            logger.warning(f"Detected Knowledge Gap: {request.question}")
            # Check if this gap already exists
            stmt = select(KnowledgeGap).where(
                KnowledgeGap.workspace_id == workspace_id,
                KnowledgeGap.query == request.question
            )
            res = await db.execute(stmt)
            existing_gap = res.scalars().first()
            
            if existing_gap:
                existing_gap.frequency += 1
                existing_gap.max_retrieval_score = max(existing_gap.max_retrieval_score, max_score if not using_multi_agent else confidence)
                existing_gap.last_encountered_at = datetime.utcnow()
            else:
                new_gap = KnowledgeGap(
                    workspace_id=workspace_id,
                    query=request.question,
                    max_retrieval_score=max_score if not using_multi_agent else confidence
                )
                db.add(new_gap)

        if not using_multi_agent:
            # Legacy path - generate answer from chunks
            if not chunks:
                answer_text = "I couldn't find this in your company's knowledge base. I have logged this as a knowledge gap for the team to address."
                sources = []
            else:
                answer = await generator.generate_answer(request.question, chunks)
                answer_text = answer.answer_text
                sources = [Source(title=s["title"], url=s["url"]) for s in answer.sources]

        # 3. Persist to QueryLog
        query_log = QueryLog(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            question=request.question,
            answer=answer_text,
            sources=[s.dict() for s in sources]
        )
        db.add(query_log)
        
        # Update conversation timestamp
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await db.execute(stmt)
        conv = result.scalar_one()
        conv.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(query_log)

        return QueryResponse(
            answer=answer_text,
            sources=sources,
            query_id=query_log.id,
            conversation_id=conversation_id
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")
