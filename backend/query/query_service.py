import logging
import json
from datetime import datetime
from typing import List, Optional, AsyncGenerator, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.generation.stream_generator import StreamGenerator
from backend.reasoning.orchestrator import ReasoningOrchestrator
from backend.reasoning.supervisor import SupervisorAgent, QueryIntent
from backend.models.query_log import QueryLog
from backend.models.conversation import Conversation
from backend.models.user import User
from backend.query.semantic_cache import SemanticCache
from backend.query.resolution import QueryResult, QueryResolutionPlan

logger = logging.getLogger(__name__)

class QueryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.cache = SemanticCache()

    async def _get_or_create_conversation(self, workspace_id: str, question: str, conversation_id: Optional[str] = None) -> str:
        if conversation_id:
            return conversation_id
        
        new_conv = Conversation(
            workspace_id=workspace_id,
            title=question[:50] + "..." if len(question) > 50 else question
        )
        self.db.add(new_conv)
        await self.db.commit()
        await self.db.refresh(new_conv)
        return new_conv.id

    async def execute_query(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        reasoning_mode: bool = False
    ) -> QueryResult:
        """
        Core business logic for querying the knowledge base.
        """
        # 1. Handle Conversation
        conversation_id = await self._get_or_create_conversation(workspace_id, question, conversation_id)
        
        # 1.5 Semantic Cache Check
        cached_result = await self.cache.check_cache(workspace_id, question)
        if cached_result:
            query_log = QueryLog(
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                question=question,
                answer=cached_result["answer"],
                sources=cached_result["sources"]
            )
            self.db.add(query_log)
            
            # Update conversation timestamp
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            result = await self.db.execute(stmt)
            conv = result.scalar_one()
            conv.updated_at = datetime.utcnow()
            
            await self.db.commit()
            await self.db.refresh(query_log)
            
            return QueryResult(
                answer=cached_result["answer"],
                sources=cached_result["sources"],
                query_id=query_log.id,
                conversation_id=conversation_id,
                metadata={"method": "semantic_cache", "similarity": cached_result["similarity"]}
            )

        # 2. Dynamic Intent Routing
        supervisor = SupervisorAgent()
        
        if reasoning_mode:
            plan = QueryResolutionPlan(
                query=question,
                intent=QueryIntent.DEEP_ANALYSIS.value,
                required_tools=[]
            )
        else:
            classification = await supervisor.classify_intent(question)
            plan = QueryResolutionPlan(
                query=question,
                intent=classification.intent.value,
                reasoning=getattr(classification, "reasoning", None),
                required_tools=getattr(classification, "required_tools", [])
            )
        intent = QueryIntent(plan.intent)
        logger.info(f"Query mapped to intent: {intent} (Reasoning: {plan.reasoning})")

        answer_text = ""
        sources = []
        confidence = 0.0
        metadata = {}

        # All queries route to the LangGraph ReasoningOrchestrator for unified execution
        reasoning_orchestrator = ReasoningOrchestrator()
        reason_result = await reasoning_orchestrator.run_durable(
            query=question,
            workspace_id=workspace_id,
            user_id=user_id,
            max_iterations=5
        )
        
        answer_text = reason_result.get("answer")
        if not answer_text:
            answer_text = "Reasoning execution started but did not complete synchronously."
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

        # 3. Persist to QueryLog
        query_log = QueryLog(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            question=question,
            answer=answer_text,
            sources=sources
        )
        self.db.add(query_log)
        
        # Update cache
        await self.cache.set_cache(workspace_id, question, {"answer": answer_text, "sources": sources})
        
        # Update conversation timestamp
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conv = result.scalar_one()
        conv.updated_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(query_log)

        return QueryResult(
            answer=answer_text,
            sources=sources,
            query_id=query_log.id,
            conversation_id=conversation_id,
            metadata=metadata
        )

    async def stream_query(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        reasoning_mode: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Core business logic for streaming queries. Resolves threads and saves logs.
        """
        supervisor = SupervisorAgent()
        
        # 1. Resolve and yield conversation thread
        conversation_id = await self._get_or_create_conversation(workspace_id, question, conversation_id)
        yield f"data: {json.dumps({'type': 'conversation', 'conversation_id': conversation_id})}\n\n"
        
        yield f"data: {json.dumps({'type': 'status', 'status': 'Analyzing query intent...'})}\n\n"
        
        if reasoning_mode:
            plan = QueryResolutionPlan(
                query=question,
                intent=QueryIntent.DEEP_ANALYSIS.value,
                required_tools=[]
            )
        else:
            classification = await supervisor.classify_intent(question)
            plan = QueryResolutionPlan(
                query=question,
                intent=classification.intent.value,
                reasoning=getattr(classification, "reasoning", None),
                required_tools=getattr(classification, "required_tools", [])
            )
        intent = QueryIntent(plan.intent)
            
        yield f"data: {json.dumps({'type': 'status', 'status': f'Intent classified as: {intent.value}'})}\n\n"

        answer_text = ""
        sources = []

        # All queries route to LangGraph ReasoningOrchestrator for unified execution
        yield f"data: {json.dumps({'type': 'status', 'status': 'Initializing reasoning swarm...'})}\n\n"
        reasoning_orchestrator = ReasoningOrchestrator()
        
        reason_result = await reasoning_orchestrator.run_durable(
            query=question,
            workspace_id=workspace_id,
            user_id=user_id,
            max_iterations=5
        )
        
        if "answer" in reason_result and reason_result["answer"]:
            answer_text = reason_result["answer"]
            yield f"data: {json.dumps({'type': 'token', 'token': answer_text})}\n\n"
        else:
            answer_text = "Reasoning execution paused for user input or did not complete."
            yield f"data: {json.dumps({'type': 'status', 'status': answer_text})}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'token': answer_text})}\n\n"

        # 3. Persist to QueryLog and Cache
        if answer_text:
            try:
                query_log = QueryLog(
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    question=question,
                    answer=answer_text,
                    sources=sources
                )
                self.db.add(query_log)
                await self.cache.set_cache(workspace_id, question, {"answer": answer_text, "sources": sources})
                
                # Update conversation timestamp
                stmt = select(Conversation).where(Conversation.id == conversation_id)
                result = await self.db.execute(stmt)
                conv = result.scalar_one()
                conv.updated_at = datetime.utcnow()
                await self.db.commit()
            except Exception as e:
                logger.error(f"Failed to save streamed query to database: {e}")
                await self.db.rollback()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

