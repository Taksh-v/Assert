"""
Query Service — task2_!!!! Comprehensive Rewrite

The central orchestrator for the Assest response system. Routes queries
through the Adaptive Router → appropriate tier → CRAG verification →
citation-grounded generation → SSE streaming.

Key changes from previous version:
- Adaptive 3-tier routing (DIRECT / FAST_RAG / FULL_SWARM)
- CRAG verification before generation
- Multi-turn conversation memory (last 6 messages)
- Structured SSE events with sources and metadata
- Sources properly propagated in all paths
"""
import logging
import json
from datetime import datetime
import asyncio
import random
from typing import List, Optional, AsyncGenerator, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import uuid

from backend.query.adaptive_router import AdaptiveRouter, RouteDecision
from backend.query.crag_verifier import CRAGVerifier, KnowledgeGapHandler
from backend.query.generator import Generator, Answer
from backend.query.retriever import Retriever
from backend.query.resolution import (
    QueryResult,
    QueryResolutionPlan,
    ResponseTier,
    CitedSource,
)
from backend.generation.stream_generator import StreamGenerator
from backend.reasoning.orchestrator import ReasoningOrchestrator
from backend.reasoning.supervisor import SupervisorAgent, QueryIntent
from backend.models.query_log import QueryLog
from backend.models.conversation import Conversation
from backend.models.user import User
from backend.query.semantic_cache import SemanticCache
from backend.observability.telemetry import tracer
from backend.core.config import get_settings
from backend.core.database import async_session

logger = logging.getLogger(__name__)
from backend.core import metrics
settings = get_settings()


class QueryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.cache = SemanticCache()
        self.router = AdaptiveRouter()
        self.retriever = Retriever()
        self.crag = CRAGVerifier()
        self.gap_handler = KnowledgeGapHandler()
        self.generator = Generator()
        self._reasoning_orchestrator = None

    def _get_reasoning_orchestrator(self):
        """Lazy-init singleton to avoid rebuilding LangGraph workflow per query."""
        if self._reasoning_orchestrator is None:
            self._reasoning_orchestrator = ReasoningOrchestrator()
        return self._reasoning_orchestrator

    def _should_run_quality_eval(self, confidence_score: float = 1.0) -> bool:
        if not getattr(settings, "enable_online_evaluations", False):
            return False
        sample_rate = float(getattr(settings, "online_evaluation_sample_rate", 0.05))
        if confidence_score < 0.4:
            sample_rate = max(sample_rate, 0.5)
        return random.random() < min(max(sample_rate, 0.0), 1.0)

    def _quality_eval_defaults(self, answer_text: str, reasoning: str) -> tuple[float, float, str]:
        return 1.0, 1.0, reasoning or "Quality evaluation skipped by policy."

    async def _handle_system_metadata_query(
        self, question: str, workspace_id: str, session: Optional[AsyncSession] = None
    ) -> Optional[tuple[str, List[Dict[str, str]]]]:
        db = session or self.db
        """
        Check if the question is about system metadata (e.g., document count, list of documents).
        If yes, query the database directly and return (answer_text, sources).
        """
        lower = question.lower().strip()
        
        # 1. Document count query
        is_count_query = any(
            marker in lower
            for marker in ["how many documents", "number of documents", "count of documents", "document count"]
        )
        
        # 2. List documents query
        is_list_query = any(
            marker in lower
            for marker in ["what documents", "list of documents", "list all documents", "which documents", "show documents", "show all documents"]
        )
        
        if not (is_count_query or is_list_query):
            return None
            
        try:
            from backend.models.document import Document
            from sqlalchemy import func
            
            # Get total active document count
            stmt = select(func.count(Document.id)).where(
                Document.workspace_id == workspace_id,
                Document.is_active == True
            )
            res = await db.execute(stmt)
            count = res.scalar() or 0
            
            # Get list of documents
            stmt = select(Document.title, Document.source_url).where(
                Document.workspace_id == workspace_id,
                Document.is_active == True
            ).order_by(Document.title.asc()).limit(30)
            res = await db.execute(stmt)
            docs = res.all()
            
            if is_count_query:
                answer = f"There are currently {count} active documents in your company's knowledge base."
                if docs:
                    doc_list = "\n".join(f"- {d[0]}" for d in docs[:10])
                    answer += f"\n\nHere are some of them:\n{doc_list}"
                    if count > 10:
                        answer += f"\n...and {count - 10} more."
            else: # is_list_query
                if count == 0:
                    answer = "There are currently no active documents in the system."
                else:
                    doc_list = "\n".join(f"- [{d[0]}]({d[1]})" if d[1] else f"- {d[0]}" for d in docs)
                    answer = f"Here are the {count} active documents in the system:\n{doc_list}"
                    
            sources = [{"title": d[0], "url": d[1] or ""} for d in docs if d[0]]
            return answer, sources
            
        except Exception as e:
            logger.warning("Failed to resolve system metadata query directly: %s", e)
            return None

    # ── Conversation management ────────────────────────────

    async def _get_or_create_conversation(
        self, workspace_id: str, question: str, conversation_id: Optional[str] = None, session: Optional[AsyncSession] = None
    ) -> str:
        if conversation_id:
            return conversation_id

        db = session or self.db
        new_conv = Conversation(
            workspace_id=workspace_id,
            title=question[:50] + "..." if len(question) > 50 else question,
        )
        db.add(new_conv)
        await db.commit()
        await db.refresh(new_conv)
        return new_conv.id

    async def _load_conversation_history(
        self,
        conversation_id: str,
        max_messages: int = 6,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, str]]:
        """
        Load the last N messages from the conversation for multi-turn context.
        Returns a list of {"role": "user"/"assistant", "content": "..."} dicts.
        """
        try:
            db = session or self.db
            stmt = (
                select(QueryLog)
                .where(QueryLog.conversation_id == conversation_id)
                .order_by(QueryLog.created_at.desc())
                .limit(max_messages)
            )
            result = await db.execute(stmt)
            messages = result.scalars().all()

            # Reverse to chronological order
            messages = list(reversed(messages))

            history = []
            for msg in messages:
                if msg.question:
                    history.append({"role": "user", "content": msg.question})
                if msg.answer:
                    history.append({"role": "assistant", "content": msg.answer})

            return history

        except Exception as e:
            logger.warning("Failed to load conversation history: %s", e)
            return []

    # ── Core query execution (non-streaming) ───────────────

    async def execute_query(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        reasoning_mode: bool = False,
        request_id: Optional[str] = None,
        context_files: Optional[List[str]] = None,
    ) -> QueryResult:
        """
        Core business logic for querying the knowledge base.
        Routes through adaptive tiers with CRAG verification.
        """
        start_ts = datetime.utcnow()
        request_id = request_id or str(uuid.uuid4())

        with tracer.start_as_current_span("query.execute") as span:
            span.set_attribute("request_id", request_id)
            span.set_attribute("workspace_id", workspace_id)
            span.set_attribute("reasoning_mode", reasoning_mode)
            span.set_attribute("user_id", str(user_id) if user_id is not None else "")

            # 1. Handle Conversation
            with tracer.start_as_current_span("query.conversation"):
                conversation_id = await self._get_or_create_conversation(
                    workspace_id, question, conversation_id
                )

            # 1.2 Resolve user's role early
            user_role = "employee"
            if user_id and workspace_id:
                try:
                    from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
                    stmt = select(WorkspaceMember.role).where(
                        WorkspaceMember.user_id == user_id,
                        WorkspaceMember.workspace_id == workspace_id
                    )
                    res = await self.db.execute(stmt)
                    db_role = res.scalar()
                    if db_role:
                        if db_role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
                            user_role = "admin"
                        else:
                            user_role = "employee"
                except Exception as e:
                    logger.warning(f"Failed to fetch workspace role: {e}")

            # 1.5 Semantic Cache Check
            with tracer.start_as_current_span("query.cache_lookup"):
                cached_result = await self.cache.check_cache(workspace_id, question, session=self.db)
            if cached_result and cached_result.get("answer", "").strip():
                span.set_attribute("query.method", "semantic_cache")
                response_time_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
                query_log = QueryLog(
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    question=question,
                    answer=cached_result["answer"],
                    sources=cached_result["sources"],
                    response_time_ms=response_time_ms,
                )
                self.db.add(query_log)

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
                    metadata={"method": "semantic_cache", "similarity": cached_result["similarity"]},
                )

            # 1.6 System Metadata Check
            sys_res = await self._handle_system_metadata_query(question, workspace_id)
            if sys_res:
                answer_text, sources = sys_res
                response_time_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
                query_log = QueryLog(
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    question=question,
                    answer=answer_text,
                    sources=sources,
                    response_time_ms=response_time_ms,
                )
                self.db.add(query_log)
                
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
                    response_tier=ResponseTier.DIRECT.value,
                    grounding_score=1.0,
                    metadata={"method": "system_metadata_query"},
                )

            # 2. Route the query
            lower = question.lower().strip()
            is_greeting = lower in self.router.GREETING_PATTERNS or (
                len(lower.split()) <= 2 and "?" not in lower
            )

            retrieval_task = None
            if not is_greeting and not reasoning_mode:
                retrieval_task = asyncio.create_task(
                    self.retriever.search(
                        question=question,
                        workspace_id=workspace_id,
                        top_k=5,
                        user_id=user_id,
                        user_role=user_role,
                        context_files=context_files,
                    )
                )

            with tracer.start_as_current_span("query.routing"):
                route = await self.router.route(question, reasoning_mode=reasoning_mode)
            logger.info(
                "Query routed: tier=%s, intent=%s, rationale=%s",
                route.tier.value,
                route.intent.value,
                route.rationale,
            )
            span.set_attribute("query.tier", route.tier.value)
            span.set_attribute("query.intent", route.intent.value)

            if route.tier != ResponseTier.FAST_RAG and retrieval_task:
                retrieval_task.cancel()

            # 3. Load conversation history for multi-turn
            with tracer.start_as_current_span("query.history"):
                history = await self._load_conversation_history(conversation_id, max_messages=6)

            # 4. Execute the appropriate path
            answer: Answer
            metadata: Dict[str, Any] = {"intent": route.intent.value, "tier": route.tier.value}

            if route.tier == ResponseTier.DIRECT:
                with tracer.start_as_current_span("query.path.direct"):
                    answer = await self._direct_path(question, history)
                metadata["method"] = "direct_conversational"

            elif route.tier == ResponseTier.FAST_RAG:
                with tracer.start_as_current_span("query.path.fast_rag"):
                    answer = await self._fast_rag_path(
                        question, workspace_id, user_id, history, pre_retrieved_task=retrieval_task, user_role=user_role, context_files=context_files
                    )
                metadata["method"] = "fast_rag_crag"

            elif route.tier == ResponseTier.FULL_SWARM:
                with tracer.start_as_current_span("query.path.full_swarm"):
                    answer = await self._full_swarm_path(question, workspace_id, user_id, history)
                metadata["method"] = "reasoning_swarm"

            elif route.tier == ResponseTier.TOOL_EXEC:
                with tracer.start_as_current_span("query.path.tool_exec"):
                    answer = await self._full_swarm_path(question, workspace_id, user_id, history)
                metadata["method"] = "tool_execution"

            else:
                with tracer.start_as_current_span("query.path.fallback_fast_rag"):
                    answer = await self._fast_rag_path(question, workspace_id, user_id, history, user_role=user_role, context_files=context_files)
                metadata["method"] = "fallback_fast_rag"

            metadata["grounding_score"] = answer.grounding_score
            metadata["response_tier"] = answer.response_tier
            metadata["faithfulness_score"] = answer.faithfulness_score
            metadata["relevance_score"] = answer.relevance_score
            metadata["eval_reasoning"] = answer.eval_reasoning
            metadata["user_profile"] = getattr(answer, "user_profile", None)

            # 5. Persist to QueryLog
            with tracer.start_as_current_span("query.persistence"):
                response_time_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
                eval_reasoning_db = answer.eval_reasoning
                if getattr(answer, "user_profile", None):
                    eval_reasoning_db += f"\n\n[USER_PROFILE]: {json.dumps(answer.user_profile)}"

                query_log = QueryLog(
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    question=question,
                    answer=answer.answer_text,
                    sources=answer.sources,
                    faithfulness_score=answer.faithfulness_score,
                    relevance_score=answer.relevance_score,
                    eval_reasoning=eval_reasoning_db,
                    response_time_ms=response_time_ms,
                )
                self.db.add(query_log)

                # Update cache
                if answer.answer_text and answer.answer_text.strip():
                    await self.cache.set_cache(
                        workspace_id,
                        question,
                        {"answer": answer.answer_text, "sources": answer.sources},
                    )


                # Update conversation timestamp
                stmt = select(Conversation).where(Conversation.id == conversation_id)
                result = await self.db.execute(stmt)
                conv = result.scalar_one()
                conv.updated_at = datetime.utcnow()

                await self.db.commit()
                await self.db.refresh(query_log)

            return QueryResult(
                answer=answer.answer_text,
                sources=answer.sources,
                citations=[c.model_dump() for c in answer.citations],
                citations_used=answer.citations_used,
                query_id=query_log.id,
                conversation_id=conversation_id,
                response_tier=answer.response_tier,
                grounding_score=answer.grounding_score,
                metadata=metadata,
            )

    # ── Response tier paths ────────────────────────────────

    async def _direct_path(
        self,
        question: str,
        history: List[Dict[str, str]],
    ) -> Answer:
        """DIRECT tier: no retrieval, conversational response."""
        answer = await self.generator.generate_direct_response(
            question=question,
            conversation_history=history if history else None,
        )
        answer.relevance_score = 1.0
        answer.eval_reasoning = "Faithfulness: N/A\n\nRelevance evaluation skipped by policy."
        answer.faithfulness_score = 1.0  # N/A for direct path
        return answer

    async def _fast_rag_path(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        history: List[Dict[str, str]],
        pre_retrieved_task: Optional[asyncio.Task] = None,
        user_role: Optional[str] = "employee",
        context_files: Optional[List[str]] = None,
    ) -> Answer:
        """FAST_RAG tier: retrieve → CRAG verify → generate with citations."""
        # Resolve user's role if not passed or is default
        if user_id and workspace_id and (not user_role or user_role == "employee"):
            try:
                from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
                stmt = select(WorkspaceMember.role).where(
                    WorkspaceMember.user_id == user_id,
                    WorkspaceMember.workspace_id == workspace_id
                )
                res = await self.db.execute(stmt)
                db_role = res.scalar()
                if db_role:
                    if db_role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
                        user_role = "admin"
                    else:
                        user_role = "employee"
            except Exception as e:
                logger.warning(f"Failed to fetch workspace role: {e}")

        # 1. Retrieve
        if pre_retrieved_task:
            try:
                chunks = await pre_retrieved_task
            except Exception as e:
                logger.error("Speculative retrieval task failed, falling back to synchronous search: %s", e)
                chunks = await self.retriever.search(
                    question=question,
                    workspace_id=workspace_id,
                    top_k=5,
                    user_id=user_id,
                    user_role=user_role
                )
        else:
            chunks = await self.retriever.search(
                question=question,
                workspace_id=workspace_id,
                top_k=5,
                user_id=user_id,
                user_role=user_role,
                context_files=context_files,
            )


        # 2. CRAG Verify
        verified = await self.crag.verify(
            question=question,
            chunks=chunks,
            workspace_id=workspace_id,
        )

        # 3. Handle knowledge gaps
        if verified.needs_web_fallback:
            gap_result = await self.gap_handler.handle_gap(question, workspace_id)
            answer_text = gap_result["answer"]
            
            # Simple context string from fallback sources
            context_str = "\n\n".join([s.get("title", "") + ": " + s.get("url", "") for s in gap_result.get("sources", [])])
            if self._should_run_quality_eval(verified.grounding_score):
                from backend.query.evaluators import evaluate_faithfulness, evaluate_relevance

                faith_task = evaluate_faithfulness(context_str, answer_text)
                relevance_task = evaluate_relevance(question, answer_text)
                faith_eval, relevance_eval = await asyncio.gather(faith_task, relevance_task)
                faithfulness_score = faith_eval["score"]
                relevance_score = relevance_eval["score"]
                eval_reasoning = f"Faithfulness: {faith_eval['reasoning']}\n\nRelevance: {relevance_eval['reasoning']}"
            else:
                faithfulness_score, relevance_score, eval_reasoning = self._quality_eval_defaults(
                    answer_text,
                    "Faithfulness: N/A\n\nRelevance evaluation skipped by policy.",
                )

            disclaimer = gap_result.get("disclaimer")
            if not disclaimer and (faithfulness_score < 0.70 or relevance_score < 0.70):
                disclaimer = "⚠️ This response could not be fully verified against internal documents. Please review with caution."

            return Answer(
                answer_text=answer_text,
                sources=gap_result["sources"],
                grounding_score=gap_result["grounding_score"],
                response_tier=ResponseTier.FAST_RAG.value,
                disclaimer=disclaimer,
                faithfulness_score=faithfulness_score,
                relevance_score=relevance_score,
                eval_reasoning=eval_reasoning,
            )

        # 4. Generate grounded response with citations
        answer = await self.generator.generate_grounded_response(
            question=question,
            verified_context=verified,
            tier=ResponseTier.FAST_RAG,
            conversation_history=history if history else None,
        )

        # Apply value alignment and ethical filtering to verify response neutrality and security
        from backend.query.cognitive_alignment import ValueAlignmentFilter
        value_filter = ValueAlignmentFilter()
        answer.answer_text = await value_filter.filter_values(question, answer.answer_text)


        # Run evaluations only when policy allows them.
        if self._should_run_quality_eval(verified.grounding_score):
            from backend.query.evaluators import evaluate_faithfulness, evaluate_relevance

            context_str = "\n\n".join([c.content for c in verified.verified_chunks])
            faith_task = evaluate_faithfulness(context_str, answer.answer_text)
            relevance_task = evaluate_relevance(question, answer.answer_text)
            faith_eval, relevance_eval = await asyncio.gather(faith_task, relevance_task)

            answer.faithfulness_score = faith_eval["score"]
            answer.relevance_score = relevance_eval["score"]
            answer.eval_reasoning = f"Faithfulness: {faith_eval['reasoning']}\n\nRelevance: {relevance_eval['reasoning']}"
            
            if faith_eval["score"] < 0.70 or relevance_eval["score"] < 0.70:
                answer.disclaimer = "⚠️ This response could not be fully verified against internal documents. Please review with caution."
        else:
            answer.faithfulness_score = verified.grounding_score
            answer.relevance_score = 1.0
            answer.eval_reasoning = "Faithfulness: N/A\n\nRelevance evaluation skipped by policy."

        return answer

    async def _full_swarm_path(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        history: List[Dict[str, str]],
    ) -> Answer:
        """FULL_SWARM tier: multi-agent reasoning orchestrator."""
        reasoning_orchestrator = self._get_reasoning_orchestrator()
        reason_result = await reasoning_orchestrator.run_durable(
            query=question,
            workspace_id=workspace_id,
            user_id=user_id,
            max_iterations=5,
        )

        answer_text = reason_result.get("answer") or ""
        if not answer_text:
            answer_text = "Reasoning execution started but did not complete synchronously."
        else:
            # Apply value alignment and ethical filtering to verify response neutrality and security
            from backend.query.cognitive_alignment import ValueAlignmentFilter
            value_filter = ValueAlignmentFilter()
            answer_text = await value_filter.filter_values(question, answer_text)

        confidence = reason_result.get("confidence", 0.0)


        if self._should_run_quality_eval(confidence):
            from backend.query.evaluators import evaluate_relevance

            relevance_eval = await evaluate_relevance(question, answer_text)
            relevance_score = relevance_eval["score"]
            eval_reasoning = f"Faithfulness (confidence): {confidence:.2f}\n\nRelevance: {relevance_eval['reasoning']}"
        else:
            relevance_score = 1.0
            eval_reasoning = "Faithfulness (confidence): {0:.2f}\n\nRelevance evaluation skipped by policy.".format(confidence)

        disclaimer = None
        if confidence < 0.70 or relevance_score < 0.70:
            disclaimer = "⚠️ This response could not be fully verified against internal documents. Please review with caution."

        return Answer(
            answer_text=answer_text,
            sources=[],
            grounding_score=confidence,
            response_tier=ResponseTier.FULL_SWARM.value,
            faithfulness_score=confidence,  # confidence functions as grounding/faithfulness score
            relevance_score=relevance_score,
            eval_reasoning=eval_reasoning,
            disclaimer=disclaimer,
            user_profile=reason_result.get("user_profile"),
        )

    # ── Streaming query ────────────────────────────────────

    async def stream_query(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        reasoning_mode: bool = False,
        request_id: Optional[str] = None,
        context_files: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Core streaming logic wrapper that buffers token output chunks to yield batches of 3–5 tokens/words.
        """
        req_id = request_id or str(uuid.uuid4())
        raw_stream = self._stream_query_raw(
            question=question,
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            reasoning_mode=reasoning_mode,
            request_id=req_id,
            context_files=context_files,
        )

        token_buffer = []
        is_first_token = True

        def has_punctuation(text: str) -> bool:
            return any(c in text for c in (".", "?", "!", "\n", ";"))

        async for chunk in raw_stream:
            if chunk.startswith("data:"):
                try:
                    payload_str = chunk[5:].strip()
                    payload = json.loads(payload_str)
                    if payload.get("type") == "token":
                        token_text = payload.get("token", "")
                        token_buffer.append(token_text)

                        # Flush if it's the first token, contains end-of-phrase punctuation/newlines,
                        # or if buffer has reached 4 items.
                        should_flush = (
                            is_first_token or 
                            has_punctuation(token_text) or 
                            len(token_buffer) >= 4
                        )

                        if should_flush:
                            concatenated = "".join(token_buffer)
                            token_buffer.clear()
                            is_first_token = False
                            yield f"data: {json.dumps({'type': 'token', 'token': concatenated, 'request_id': req_id})}\n\n"
                        continue
                except Exception as e:
                    logger.warning(f"Error in token buffering chunk: {e}")

            # For any non-token event, flush the current buffer first to preserve message order
            if token_buffer:
                concatenated = "".join(token_buffer)
                token_buffer.clear()
                yield f"data: {json.dumps({'type': 'token', 'token': concatenated, 'request_id': req_id})}\n\n"

            yield chunk

        # Flush any remaining tokens left in the buffer at the end of the stream
        if token_buffer:
            concatenated = "".join(token_buffer)
            token_buffer.clear()
            yield f"data: {json.dumps({'type': 'token', 'token': concatenated, 'request_id': req_id})}\n\n"

    async def _stream_query_raw(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        reasoning_mode: bool = False,
        request_id: Optional[str] = None,
        context_files: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Core raw streaming logic with adaptive routing, CRAG verification,
        structured SSE events, and multi-turn conversation context.
        """
        start_ts = datetime.utcnow()
        request_id = request_id or str(uuid.uuid4())
        lower = question.lower().strip()
        is_greeting = lower in self.router.GREETING_PATTERNS or (
            len(lower.split()) <= 2 and "?" not in lower
        )

        # Resolve role, conversation thread, system metadata, and history inside short-lived DB transaction to release locks early
        user_role = "employee"
        cached_result = None
        async with async_session() as session:
            if user_id and workspace_id:
                try:
                    from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
                    stmt = select(WorkspaceMember.role).where(
                        WorkspaceMember.user_id == user_id,
                        WorkspaceMember.workspace_id == workspace_id
                    )
                    res = await session.execute(stmt)
                    db_role = res.scalar()
                    if db_role:
                        if db_role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
                            user_role = "admin"
                        else:
                            user_role = "employee"
                except Exception as e:
                    logger.warning(f"Failed to fetch workspace role: {e}")

            # 1. Resolve conversation thread
            with tracer.start_as_current_span("query.conversation"):
                conversation_id = await self._get_or_create_conversation(
                    workspace_id, question, conversation_id, session=session
                )

            # 1.5 Semantic Cache Check
            with tracer.start_as_current_span("query.cache_lookup"):
                cached_result = await self.cache.check_cache(workspace_id, question, session=session)

            # 1.6 System Metadata Check (only on cache miss)
            sys_res = None
            if not cached_result:
                sys_res = await self._handle_system_metadata_query(question, workspace_id, session=session)

            # 3. Load conversation history
            with tracer.start_as_current_span("query.history"):
                history = await self._load_conversation_history(conversation_id, max_messages=6, session=session)

        retrieval_task = None
        if not is_greeting and not reasoning_mode and not cached_result:
            retrieval_task = asyncio.create_task(
                self.retriever.search(
                    question=question,
                    workspace_id=workspace_id,
                    top_k=5,
                    user_id=user_id,
                    user_role=user_role,
                    context_files=context_files,
                )
            )

        with tracer.start_as_current_span("query.stream") as span:
            span.set_attribute("request_id", request_id)
            span.set_attribute("workspace_id", workspace_id)
            span.set_attribute("reasoning_mode", reasoning_mode)

            yield f"data: {json.dumps({'type': 'conversation', 'conversation_id': conversation_id, 'request_id': request_id})}\n\n"

            if cached_result and cached_result.get("answer", "").strip():
                yield f"data: {json.dumps({'type': 'status', 'status': 'Generating response...', 'phase': 'generation', 'request_id': request_id})}\n\n"
                sources = cached_result["sources"]
                citations_data = [{"id": i+1, "title": s["title"], "url": s["url"]} for i, s in enumerate(sources)]
                yield f"data: {json.dumps({'type': 'sources', 'sources': citations_data, 'request_id': request_id})}\n\n"
                
                answer_text = cached_result["answer"]
                words = answer_text.split(" ")
                chunk_size = 15
                for i in range(0, len(words), chunk_size):
                    chunk_text = " ".join(words[i:i+chunk_size]) + " "
                    yield f"data: {json.dumps({'type': 'token', 'token': chunk_text, 'request_id': request_id})}\n\n"
                    await asyncio.sleep(0.001)
                
                yield f"data: {json.dumps({'type': 'status', 'status': 'Done', 'phase': 'synthesis', 'request_id': request_id})}\n\n"
                meta_payload = {
                    "type": "metadata",
                    "grounding_score": 1.0,
                    "intent": "cached",
                    "tier": "direct",
                    "request_id": request_id,
                    "faithfulness_score": 1.0,
                    "relevance_score": 1.0,
                    "eval_reasoning": f"Semantic cache hit. Similarity: {cached_result.get('similarity', 1.0):.2f}"
                }
                yield f"data: {json.dumps(meta_payload)}\n\n"
                
                total_seconds = (datetime.utcnow() - start_ts).total_seconds()
                response_time_ms = int(total_seconds * 1000)
                try:
                    async with async_session() as write_session:
                        query_log = QueryLog(
                            workspace_id=workspace_id,
                            conversation_id=conversation_id,
                            question=question,
                            answer=answer_text,
                            sources=sources,
                            request_id=request_id,
                            faithfulness_score=1.0,
                            relevance_score=1.0,
                            eval_reasoning=f"Semantic cache hit. Similarity: {cached_result.get('similarity', 1.0):.2f}",
                            response_time_ms=response_time_ms,
                        )
                        write_session.add(query_log)
                        
                        stmt = select(Conversation).where(Conversation.id == conversation_id)
                        res_c = await write_session.execute(stmt)
                        conv = res_c.scalar_one()
                        conv.updated_at = datetime.utcnow()
                        await write_session.commit()
                except Exception as e:
                    logger.error("Failed to save cached query to database: %s", e)
                yield f"data: {json.dumps({'type': 'done', 'request_id': request_id})}\n\n"
                return

            if sys_res:
                answer_text, sources = sys_res
                # Stream the metadata answer
                yield f"data: {json.dumps({'type': 'status', 'status': 'Generating response...', 'phase': 'generation', 'request_id': request_id})}\n\n"
                
                # Emit sources
                citations_data = [{"id": i+1, "title": s["title"], "url": s["url"]} for i, s in enumerate(sources)]
                yield f"data: {json.dumps({'type': 'sources', 'sources': citations_data, 'request_id': request_id})}\n\n"
                
                # Stream answer tokens in chunks
                words = answer_text.split(" ")
                chunk_size = 15
                for i in range(0, len(words), chunk_size):
                    chunk_text = " ".join(words[i:i+chunk_size]) + " "
                    yield f"data: {json.dumps({'type': 'token', 'token': chunk_text, 'request_id': request_id})}\n\n"
                    await asyncio.sleep(0.001)
                
                yield f"data: {json.dumps({'type': 'status', 'status': 'Done', 'phase': 'synthesis', 'request_id': request_id})}\n\n"
                yield f"data: {json.dumps({'type': 'metadata', 'grounding_score': 1.0, 'intent': 'conversational', 'tier': 'direct', 'request_id': request_id, 'faithfulness_score': 1.0, 'relevance_score': 1.0, 'eval_reasoning': 'Metadata query resolved via local database.'})}\n\n"
                
                # Persist to database using fresh transaction
                total_seconds = (datetime.utcnow() - start_ts).total_seconds()
                response_time_ms = int(total_seconds * 1000)
                try:
                    async with async_session() as write_session:
                        query_log = QueryLog(
                            workspace_id=workspace_id,
                            conversation_id=conversation_id,
                            question=question,
                            answer=answer_text,
                            sources=sources,
                            request_id=request_id,
                            faithfulness_score=1.0,
                            relevance_score=1.0,
                            eval_reasoning="Metadata query resolved via local database.",
                            response_time_ms=response_time_ms,
                        )
                        write_session.add(query_log)
                        await write_session.commit()
                except Exception as e:
                    logger.error("Failed to save metadata query to database: %s", e)
                yield f"data: {json.dumps({'type': 'done', 'request_id': request_id})}\n\n"
                if retrieval_task:
                    retrieval_task.cancel()
                return

            # 2. Route the query
            yield f"data: {json.dumps({'type': 'status', 'status': 'Analyzing query intent...', 'phase': 'routing', 'request_id': request_id})}\n\n"

            with tracer.start_as_current_span("query.routing"):
                route = await self.router.route(question, reasoning_mode=reasoning_mode)

            span.set_attribute("query.tier", route.tier.value)
            span.set_attribute("query.intent", route.intent.value)

            yield f"data: {json.dumps({'type': 'status', 'status': f'Route: {route.tier.value} ({route.intent.value})', 'phase': 'routing', 'request_id': request_id})}\n\n"

            if route.tier != ResponseTier.FAST_RAG and retrieval_task:
                retrieval_task.cancel()

        answer_text = ""
        sources = []
        citations_data = []
        grounding_score = 0.0
        start_ts = datetime.utcnow()

        # ── DIRECT PATH (no retrieval) ──
        if route.tier == ResponseTier.DIRECT:
            yield f"data: {json.dumps({'type': 'status', 'status': 'Generating response...', 'phase': 'generation', 'request_id': request_id})}\n\n"

            sg = StreamGenerator()
            messages = []
            if history:
                for h in history[-4:]:  # Last 2 Q&A pairs for direct
                    messages.append({"role": h["role"], "content": h["content"]})
            messages.append({"role": "user", "content": question})

            try:
                with tracer.start_as_current_span("query.path.direct"):
                    async for chunk in sg.stream_chat(
                        messages,
                        request_id=request_id,
                        max_tokens=128,
                        prompt_cache_key="direct-stream:v1",
                    ):
                        yield chunk
                        try:
                            raw = chunk.strip()
                            if raw.startswith("data:"):
                                payload = json.loads(raw[len("data:"):].strip())
                                if payload.get("type") == "token":
                                    answer_text += payload.get("token", "")
                                    try:
                                        metrics.record_stream_token(workspace_id=workspace_id)
                                    except Exception:
                                        pass
                                elif payload.get("type") == "done":
                                    break
                        except Exception:
                            pass
            except Exception as e:
                logger.error("Direct streaming failed: %s", e)

        # ── FAST_RAG PATH ──
        elif route.tier == ResponseTier.FAST_RAG:
            # Retrieve
            yield f"data: {json.dumps({'type': 'status', 'status': 'Searching knowledge base...', 'phase': 'retrieval', 'request_id': request_id})}\n\n"

            with tracer.start_as_current_span("query.path.fast_rag.retrieval"):
                if retrieval_task:
                    try:
                        chunks = await retrieval_task
                    except Exception as e:
                        logger.error("Speculative retrieval task failed in stream, falling back to sync search: %s", e)
                        chunks = await self.retriever.search(
                            question=question,
                            workspace_id=workspace_id,
                            top_k=5,
                            user_id=user_id,
                            user_role=user_role,
                        )
                else:
                    chunks = await self.retriever.search(
                        question=question,
                        workspace_id=workspace_id,
                        top_k=5,
                        user_id=user_id,
                        user_role=user_role,
                    )

            # CRAG Verify
            yield f"data: {json.dumps({'type': 'status', 'status': 'Verifying source relevance...', 'phase': 'verification', 'request_id': request_id})}\n\n"

            with tracer.start_as_current_span("query.path.fast_rag.verification"):
                verified = await self.crag.verify(
                    question=question,
                    chunks=chunks,
                    workspace_id=workspace_id,
                )

            grounding_score = verified.grounding_score

            # Handle knowledge gaps
            if verified.needs_web_fallback:
                yield f"data: {json.dumps({'type': 'status', 'status': 'Knowledge gap detected, trying fallback...', 'phase': 'fallback', 'request_id': request_id})}\n\n"
                with tracer.start_as_current_span("query.path.fast_rag.fallback"):
                    gap_result = await self.gap_handler.handle_gap(question, workspace_id)
                answer_text = gap_result["answer"]
                sources = gap_result["sources"]
                grounding_score = gap_result["grounding_score"]

                # Stream the gap answer in chunks
                words = answer_text.split(" ")
                chunk_size = 15
                for i in range(0, len(words), chunk_size):
                    chunk_text = " ".join(words[i:i+chunk_size]) + " "
                    yield f"data: {json.dumps({'type': 'token', 'token': chunk_text, 'request_id': request_id})}\n\n"
                    await asyncio.sleep(0.001)

            else:
                # Emit sources BEFORE generation starts
                from backend.query.generator import build_citation_manifest
                _, citation_list = build_citation_manifest(chunks=verified.verified_chunks)
                citations_data = [c.model_dump() for c in citation_list]
                
                yield f"data: {json.dumps({'type': 'sources', 'sources': citations_data, 'request_id': request_id})}\n\n"

                # Generate grounded response
                yield f"data: {json.dumps({'type': 'status', 'status': 'Generating grounded response...', 'phase': 'generation', 'request_id': request_id})}\n\n"

                answer_text = ""
                try:
                    with tracer.start_as_current_span("query.path.fast_rag.generation"):
                        async for token in self.generator.stream_grounded_response(
                            question=question,
                            verified_context=verified,
                            tier=ResponseTier.FAST_RAG,
                            conversation_history=history if history else None,
                        ):
                            answer_text += token
                            yield f"data: {json.dumps({'type': 'token', 'token': token, 'request_id': request_id})}\n\n"
                    # Post-process generated text to sanitize and extract actual cited sources
                    from backend.query.generator import extract_citations_used
                    answer_text = self.generator._sanitize_output(answer_text, "", "")
                    used = extract_citations_used(answer_text)
                    cited_sources = [c for c in citation_list if c.id in used]
                    sources = [{"title": c.title, "url": c.url} for c in cited_sources]
                except Exception as e:
                    logger.error("Streaming grounded response failed: %s", e)
                    # Yield fallback tokens
                    best = verified.verified_chunks[0].content.strip() if verified.verified_chunks else ""
                    fallback_text = best[:900] or "I couldn't find this in your company's knowledge base."
                    words = fallback_text.split(" ")
                    chunk_size = 15
                    for i in range(0, len(words), chunk_size):
                        chunk_text = " ".join(words[i:i+chunk_size]) + " "
                        yield f"data: {json.dumps({'type': 'token', 'token': chunk_text, 'request_id': request_id})}\n\n"
                        await asyncio.sleep(0.001)
                    answer_text = fallback_text
                    used = [1] if verified.verified_chunks else []
                    cited_sources = [c for c in citation_list if c.id in used]
                    sources = [{"title": c.title, "url": c.url} for c in cited_sources]
                
                grounding_score = verified.grounding_score

        # ── FULL_SWARM PATH ──
        elif route.tier in (ResponseTier.FULL_SWARM, ResponseTier.TOOL_EXEC):
            yield f"data: {json.dumps({'type': 'status', 'status': 'Initializing reasoning swarm...', 'phase': 'swarm', 'request_id': request_id})}\n\n"

            reasoning_orchestrator = self._get_reasoning_orchestrator()
            with tracer.start_as_current_span("query.path.full_swarm"):
                reason_result = await reasoning_orchestrator.run_durable(
                    query=question,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    request_id=request_id,
                    max_iterations=5,
                )

            answer_text = reason_result.get("answer") or ""
            grounding_score = reason_result.get("confidence", 0.0)
            user_profile = reason_result.get("user_profile")

            if not answer_text:
                answer_text = "Reasoning completed but produced no output."

            yield f"data: {json.dumps({'type': 'status', 'status': f'Reasoning complete (confidence: {grounding_score:.0%})', 'phase': 'synthesis', 'request_id': request_id})}\n\n"

            # Stream the swarm answer in chunks
            words = answer_text.split(" ")
            chunk_size = 15
            for i in range(0, len(words), chunk_size):
                chunk_text = " ".join(words[i:i+chunk_size]) + " "
                yield f"data: {json.dumps({'type': 'token', 'token': chunk_text, 'request_id': request_id})}\n\n"
                await asyncio.sleep(0.001)

        context_str = ""
        if route.tier == ResponseTier.FAST_RAG and 'verified' in locals() and hasattr(verified, 'verified_chunks'):
            context_str = "\n\n".join([c.content for c in verified.verified_chunks])
        elif route.tier == ResponseTier.FAST_RAG and 'gap_result' in locals():
            context_str = "\n\n".join([s.get("title", "") + ": " + s.get("url", "") for s in gap_result.get("sources", [])])

        faithfulness_score = 1.0
        relevance_score = 1.0
        eval_reasoning = ""

        with tracer.start_as_current_span("query.evaluation"):
            should_eval = self._should_run_quality_eval(grounding_score) if route.tier != ResponseTier.DIRECT else False
            if should_eval:
                yield f"data: {json.dumps({'type': 'status', 'status': 'Running quality evaluations...', 'phase': 'evaluation', 'request_id': request_id})}\n\n"
                from backend.query.evaluators import evaluate_faithfulness, evaluate_relevance

                if route.tier == ResponseTier.DIRECT:
                    relevance_res = await evaluate_relevance(question, answer_text)
                    relevance_score = relevance_res["score"]
                    eval_reasoning = f"Faithfulness: N/A\n\nRelevance: {relevance_res['reasoning']}"
                elif route.tier == ResponseTier.FAST_RAG:
                    faith_task = evaluate_faithfulness(context_str, answer_text)
                    relevance_task = evaluate_relevance(question, answer_text)
                    faith_res, relevance_res = await asyncio.gather(faith_task, relevance_task)

                    faithfulness_score = faith_res["score"]
                    relevance_score = relevance_res["score"]
                    eval_reasoning = f"Faithfulness: {faith_res['reasoning']}\n\nRelevance: {relevance_res['reasoning']}"
                else:
                    relevance_res = await evaluate_relevance(question, answer_text)
                    relevance_score = relevance_res["score"]
                    faithfulness_score = grounding_score
                    eval_reasoning = f"Faithfulness (confidence): {grounding_score:.2f}\n\nRelevance: {relevance_res['reasoning']}"
            else:
                faithfulness_score = grounding_score if route.tier != ResponseTier.DIRECT else 1.0
                relevance_score = 1.0
                eval_reasoning = (
                    "Faithfulness: N/A\n\nRelevance evaluation skipped by policy."
                    if route.tier != ResponseTier.FULL_SWARM
                    else f"Faithfulness (confidence): {grounding_score:.2f}\n\nRelevance evaluation skipped by policy."
                )

        # Check if scores are < 0.70 and set warning disclaimer
        disclaimer = None
        if route.tier != ResponseTier.DIRECT and (faithfulness_score < 0.70 or relevance_score < 0.70):
            disclaimer = "⚠️ This response could not be fully verified against internal documents. Please review with caution."

        # ── Emit metadata event ──
        yield f"data: {json.dumps({'type': 'metadata', 'grounding_score': grounding_score, 'intent': route.intent.value, 'tier': route.tier.value, 'request_id': request_id, 'faithfulness_score': faithfulness_score, 'relevance_score': relevance_score, 'eval_reasoning': eval_reasoning, 'disclaimer': disclaimer, 'user_profile': user_profile if 'user_profile' in locals() else None})}\n\n"

        # Calculate latency
        total_seconds = (datetime.utcnow() - start_ts).total_seconds()
        response_time_ms = int(total_seconds * 1000)

        # Apply security redaction to the completed stream text before persistence/caching
        if answer_text:
            from backend.query.cognitive_alignment import ValueAlignmentFilter
            value_filter = ValueAlignmentFilter()
            answer_text = value_filter.inspect_security(answer_text)

        # ── Persist to DB using a fresh context manager session ──
        if answer_text:
            try:
                async with async_session() as write_session:
                    with tracer.start_as_current_span("query.persistence"):
                        eval_reasoning_db = eval_reasoning
                        if 'user_profile' in locals() and user_profile:
                            eval_reasoning_db += f"\n\n[USER_PROFILE]: {json.dumps(user_profile)}"

                        query_log = QueryLog(
                            workspace_id=workspace_id,
                            conversation_id=conversation_id,
                            question=question,
                            answer=answer_text,
                            sources=sources,
                            request_id=request_id,
                            faithfulness_score=faithfulness_score,
                            relevance_score=relevance_score,
                            eval_reasoning=eval_reasoning_db,
                            response_time_ms=response_time_ms,
                        )
                        write_session.add(query_log)
                        if answer_text and answer_text.strip():
                            await self.cache.set_cache(
                                workspace_id, question, {"answer": answer_text, "sources": sources}
                            )

                        stmt = select(Conversation).where(Conversation.id == conversation_id)
                        result = await write_session.execute(stmt)
                        conv = result.scalar_one()
                        conv.updated_at = datetime.utcnow()
                        await write_session.commit()
            except Exception as e:
                logger.error("Failed to save query to database: %s", e)

        # Record latency to Prometheus
        try:
            metrics.record_stream_latency(total_seconds, workspace_id=workspace_id)
        except Exception:
            pass

        yield f"data: {json.dumps({'type': 'done', 'request_id': request_id})}\n\n"
