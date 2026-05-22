import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.generation.stream_generator import StreamGenerator

logger = logging.getLogger(__name__)

from backend.query.retriever import Retriever
from backend.query.generator import Generator
from backend.retrieval.orchestrator import RetrievalOrchestrator
from backend.reasoning.orchestrator import ReasoningOrchestrator
from backend.reasoning.supervisor import SupervisorAgent, QueryIntent
from backend.reasoning.agents.quick_retriever import QuickRetrieverAgent
from backend.reasoning.agents.comparison import ComparisonAgent
from backend.api.users import get_current_user
from backend.models.user import User
from backend.core.database import get_db
from backend.api.connectors import verify_workspace_access
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
        # Phase 3 / Sprint 2: Dynamic Intent Routing via Supervisor
        supervisor = SupervisorAgent()
        
        if request.reasoning_mode:
            # Force deep analysis if explicitly requested
            classification = None
            intent = QueryIntent.DEEP_ANALYSIS
        else:
            classification = await supervisor.classify_intent(request.question)
            intent = classification.intent
            logger.info(f"Query mapped to intent: {intent} (Reasoning: {classification.reasoning})")

        start_time = datetime.utcnow()
        using_multi_agent = True
        
        if intent == QueryIntent.QUICK_LOOKUP:
            agent = QuickRetrieverAgent()
            agent_result = await agent.execute(
                query=request.question,
                workspace_id=workspace_id,
                user_id=current_user.id if current_user else None
            )
            answer_text = agent_result["answer"]
            sources = [Source(title=s, url="") for s in agent_result["sources"]]
            confidence = agent_result["confidence"]
            metadata = {"method": "quick_retriever", "intent": intent.value}
            
        elif intent == QueryIntent.COMPARISON:
            agent = ComparisonAgent()
            agent_result = await agent.execute(
                query=request.question,
                workspace_id=workspace_id,
                user_id=current_user.id if current_user else None
            )
            answer_text = agent_result["answer"]
            sources = [Source(title=s, url="") for s in agent_result["sources"]]
            confidence = agent_result["confidence"]
            metadata = {"method": "comparison_agent", "intent": intent.value}
            
        elif intent == QueryIntent.CONVERSATIONAL:
            # Bypass retrieval entirely for chit-chat
            answer_text = "I'm here to help you access your company's knowledge base. What would you like to know?"
            sources = []
            confidence = 1.0
            metadata = {"method": "conversational_bypass", "intent": intent.value}
            using_multi_agent = False
            
        elif intent == QueryIntent.ACTION_REQUEST:
            from backend.reasoning.agents.tool_executor import ToolExecutorAgent
            agent = ToolExecutorAgent()
            tool_name = classification.required_tools[0] if classification and classification.required_tools else None
            if not tool_name:
                from backend.agent.tools.registry import ToolRegistry
                registry = ToolRegistry()
                q_lower = request.question.lower()
                tool_name = next((t.name for t in registry.list_tools() if t.name in q_lower or any(w in q_lower for w in t.name.split('_'))), None)
            
            if tool_name:
                agent_result = await agent.execute(
                    query=request.question,
                    tool_name=tool_name
                )
                answer_text = agent_result["answer"]
                sources = [Source(title=s, url="") for s in agent_result["sources"]]
                confidence = agent_result["confidence"]
                metadata = {"method": "tool_executor", "tool": tool_name, "intent": intent.value}
            else:
                # Fallback to DEEP_ANALYSIS
                intent = QueryIntent.DEEP_ANALYSIS

        if intent == QueryIntent.DEEP_ANALYSIS:
            reasoning_orchestrator = ReasoningOrchestrator()
            
            # Start durable execution
            reason_result = await reasoning_orchestrator.run_durable(
                query=request.question,
                workspace_id=workspace_id,
                user_id=current_user.id if current_user else None,
                max_iterations=5
            )
            
            answer_text = reason_result.get("answer", "Reasoning execution started but did not complete synchronously.")
            sources = [] 
            confidence = reason_result.get("confidence", 0.0)
            
            metadata = {
                "method": "reasoning_swarm_p3",
                "execution_id": reason_result.get("execution_id"),
                "status": reason_result.get("status"),
                "iterations": reason_result.get("iterations"),
                "confidence": confidence,
                "intent": intent.value
            }

        max_score = confidence
        chunks = sources

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
    
    import json

    async def event_generator():
        supervisor = SupervisorAgent()
        
        # Emit status: Intent analysis
        yield f"data: {json.dumps({'type': 'status', 'status': 'Analyzing query intent...'})}\n\n"
        
        if request.reasoning_mode:
            intent = QueryIntent.DEEP_ANALYSIS
        else:
            classification = await supervisor.classify_intent(request.question)
            intent = classification.intent
            
        yield f"data: {json.dumps({'type': 'status', 'status': f'Intent classified as: {intent.value}'})}\n\n"

        if intent == QueryIntent.QUICK_LOOKUP:
            yield f"data: {json.dumps({'type': 'status', 'status': 'Retrieving context...'})}\n\n"
            orchestrator = RetrievalOrchestrator()
            context = await orchestrator.retrieve_reasoning_context(
                query=request.question,
                workspace_id=workspace_id,
                user_id=current_user.id if current_user else None
            )
            
            yield f"data: {json.dumps({'type': 'status', 'status': 'Synthesizing response...'})}\n\n"
            streamer = StreamGenerator()
            prompt = [
                {"role": "system", "content": "You are a concise, factual assistant."},
                {"role": "user", "content": f"Use ONLY the context to answer.\nContext:\n{context}\n\nQuestion: {request.question}"}
            ]
            async for event in streamer.stream_chat(prompt):
                yield event
                
        elif intent == QueryIntent.CONVERSATIONAL:
            msg = "I'm here to help you access your company's knowledge base. What would you like to know?"
            yield f"data: {json.dumps({'type': 'token', 'token': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        elif intent == QueryIntent.ACTION_REQUEST:
            yield f"data: {json.dumps({'type': 'status', 'status': 'Processing tool action...'})}\n\n"
            from backend.reasoning.agents.tool_executor import ToolExecutorAgent
            agent = ToolExecutorAgent()
            tool_name = classification.required_tools[0] if classification and classification.required_tools else None
            if not tool_name:
                from backend.agent.tools.registry import ToolRegistry
                registry = ToolRegistry()
                q_lower = request.question.lower()
                tool_name = next((t.name for t in registry.list_tools() if t.name in q_lower or any(w in q_lower for w in t.name.split('_'))), None)
            
            if tool_name:
                agent_result = await agent.execute(
                    query=request.question,
                    tool_name=tool_name
                )
                yield f"data: {json.dumps({'type': 'token', 'token': agent_result['answer']})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            else:
                intent = QueryIntent.DEEP_ANALYSIS  # Fallback
                
        if intent == QueryIntent.DEEP_ANALYSIS:
            # For deep analysis, start durable execution
            yield f"data: {json.dumps({'type': 'status', 'status': 'Initializing reasoning planner...'})}\n\n"
            reasoning_orchestrator = ReasoningOrchestrator()
            
            # Since full reasoning is multi-agent, we run it and stream steps
            reason_result = await reasoning_orchestrator.run_durable(
                query=request.question,
                workspace_id=workspace_id,
                user_id=current_user.id if current_user else None,
                max_iterations=5
            )
            
            if "answer" in reason_result:
                yield f"data: {json.dumps({'type': 'token', 'token': reason_result['answer']})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'status', 'status': 'Reasoning execution paused for user input.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
