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

logger = logging.getLogger(__name__)
from backend.core import metrics


class QueryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.cache = SemanticCache()
        self.router = AdaptiveRouter()
        self.retriever = Retriever()
        self.crag = CRAGVerifier()
        self.gap_handler = KnowledgeGapHandler()
        self.generator = Generator()

    # ── Conversation management ────────────────────────────

    async def _get_or_create_conversation(
        self, workspace_id: str, question: str, conversation_id: Optional[str] = None
    ) -> str:
        if conversation_id:
            return conversation_id

        new_conv = Conversation(
            workspace_id=workspace_id,
            title=question[:50] + "..." if len(question) > 50 else question,
        )
        self.db.add(new_conv)
        await self.db.commit()
        await self.db.refresh(new_conv)
        return new_conv.id

    async def _load_conversation_history(
        self,
        conversation_id: str,
        max_messages: int = 6,
    ) -> List[Dict[str, str]]:
        """
        Load the last N messages from the conversation for multi-turn context.
        Returns a list of {"role": "user"/"assistant", "content": "..."} dicts.
        """
        try:
            stmt = (
                select(QueryLog)
                .where(QueryLog.conversation_id == conversation_id)
                .order_by(QueryLog.created_at.desc())
                .limit(max_messages)
            )
            result = await self.db.execute(stmt)
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

            # 1.5 Semantic Cache Check
            with tracer.start_as_current_span("query.cache_lookup"):
                cached_result = await self.cache.check_cache(workspace_id, question)
            if cached_result:
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

            # 2. Route the query
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
                    answer = await self._fast_rag_path(question, workspace_id, user_id, history)
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
                    answer = await self._fast_rag_path(question, workspace_id, user_id, history)
                metadata["method"] = "fallback_fast_rag"

            metadata["grounding_score"] = answer.grounding_score
            metadata["response_tier"] = answer.response_tier
            metadata["faithfulness_score"] = answer.faithfulness_score
            metadata["relevance_score"] = answer.relevance_score
            metadata["eval_reasoning"] = answer.eval_reasoning

            # 5. Persist to QueryLog
            with tracer.start_as_current_span("query.persistence"):
                response_time_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
                query_log = QueryLog(
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    question=question,
                    answer=answer.answer_text,
                    sources=answer.sources,
                    faithfulness_score=answer.faithfulness_score,
                    relevance_score=answer.relevance_score,
                    eval_reasoning=answer.eval_reasoning,
                    response_time_ms=response_time_ms,
                )
                self.db.add(query_log)

                # Update cache
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
        from backend.query.evaluators import evaluate_relevance
        relevance_eval = await evaluate_relevance(question, answer.answer_text)
        answer.relevance_score = relevance_eval["score"]
        answer.faithfulness_score = 1.0  # N/A for direct path
        answer.eval_reasoning = f"Faithfulness: N/A\n\nRelevance: {relevance_eval['reasoning']}"
        return answer

    async def _fast_rag_path(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        history: List[Dict[str, str]],
    ) -> Answer:
        """FAST_RAG tier: retrieve → CRAG verify → generate with citations."""
        # 1. Retrieve
        chunks = await self.retriever.search(
            question=question,
            workspace_id=workspace_id,
            top_k=5,
            user_id=user_id,
        )

        # 2. CRAG Verify
        verified = await self.crag.verify(
            question=question,
            chunks=chunks,
            workspace_id=workspace_id,
        )

        from backend.query.evaluators import evaluate_faithfulness, evaluate_relevance

        # 3. Handle knowledge gaps
        if verified.needs_web_fallback:
            gap_result = await self.gap_handler.handle_gap(question, workspace_id)
            answer_text = gap_result["answer"]
            
            # Simple context string from fallback sources
            context_str = "\n\n".join([s.get("title", "") + ": " + s.get("url", "") for s in gap_result.get("sources", [])])
            faith_task = evaluate_faithfulness(context_str, answer_text)
            relevance_task = evaluate_relevance(question, answer_text)
            faith_eval, relevance_eval = await asyncio.gather(faith_task, relevance_task)

            return Answer(
                answer_text=answer_text,
                sources=gap_result["sources"],
                grounding_score=gap_result["grounding_score"],
                response_tier=ResponseTier.FAST_RAG.value,
                disclaimer=gap_result.get("disclaimer"),
                faithfulness_score=faith_eval["score"],
                relevance_score=relevance_eval["score"],
                eval_reasoning=f"Faithfulness: {faith_eval['reasoning']}\n\nRelevance: {relevance_eval['reasoning']}",
            )

        # 4. Generate grounded response with citations
        answer = await self.generator.generate_grounded_response(
            question=question,
            verified_context=verified,
            tier=ResponseTier.FAST_RAG,
            conversation_history=history if history else None,
        )

        # Run evaluations
        context_str = "\n\n".join([c.content for c in verified.verified_chunks])
        faith_task = evaluate_faithfulness(context_str, answer.answer_text)
        relevance_task = evaluate_relevance(question, answer.answer_text)
        faith_eval, relevance_eval = await asyncio.gather(faith_task, relevance_task)

        answer.faithfulness_score = faith_eval["score"]
        answer.relevance_score = relevance_eval["score"]
        answer.eval_reasoning = f"Faithfulness: {faith_eval['reasoning']}\n\nRelevance: {relevance_eval['reasoning']}"

        return answer

    async def _full_swarm_path(
        self,
        question: str,
        workspace_id: str,
        user_id: str,
        history: List[Dict[str, str]],
    ) -> Answer:
        """FULL_SWARM tier: multi-agent reasoning orchestrator."""
        reasoning_orchestrator = ReasoningOrchestrator()
        reason_result = await reasoning_orchestrator.run_durable(
            query=question,
            workspace_id=workspace_id,
            user_id=user_id,
            max_iterations=5,
        )

        answer_text = reason_result.get("answer") or ""
        if not answer_text:
            answer_text = "Reasoning execution started but did not complete synchronously."

        confidence = reason_result.get("confidence", 0.0)

        from backend.query.evaluators import evaluate_relevance
        relevance_eval = await evaluate_relevance(question, answer_text)

        return Answer(
            answer_text=answer_text,
            sources=[],
            grounding_score=confidence,
            response_tier=ResponseTier.FULL_SWARM.value,
            faithfulness_score=confidence,  # confidence functions as grounding/faithfulness score
            relevance_score=relevance_eval["score"],
            eval_reasoning=f"Faithfulness (confidence): {confidence:.2f}\n\nRelevance: {relevance_eval['reasoning']}",
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
    ) -> AsyncGenerator[str, None]:
        """
        Core streaming logic with adaptive routing, CRAG verification,
        structured SSE events, and multi-turn conversation context.
        """
        request_id = request_id or str(uuid.uuid4())
        with tracer.start_as_current_span("query.stream") as span:
            span.set_attribute("request_id", request_id)
            span.set_attribute("workspace_id", workspace_id)
            span.set_attribute("reasoning_mode", reasoning_mode)

            # 1. Resolve conversation thread
            with tracer.start_as_current_span("query.conversation"):
                conversation_id = await self._get_or_create_conversation(
                    workspace_id, question, conversation_id
                )
            yield f"data: {json.dumps({'type': 'conversation', 'conversation_id': conversation_id, 'request_id': request_id})}\n\n"

            # 2. Route the query
            yield f"data: {json.dumps({'type': 'status', 'status': 'Analyzing query intent...', 'phase': 'routing', 'request_id': request_id})}\n\n"

            with tracer.start_as_current_span("query.routing"):
                route = await self.router.route(question, reasoning_mode=reasoning_mode)

            span.set_attribute("query.tier", route.tier.value)
            span.set_attribute("query.intent", route.intent.value)

            yield f"data: {json.dumps({'type': 'status', 'status': f'Route: {route.tier.value} ({route.intent.value})', 'phase': 'routing', 'request_id': request_id})}\n\n"

            # 3. Load conversation history
            with tracer.start_as_current_span("query.history"):
                history = await self._load_conversation_history(conversation_id, max_messages=6)

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
                    async for chunk in sg.stream_chat(messages, request_id=request_id):
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
                chunks = await self.retriever.search(
                    question=question,
                    workspace_id=workspace_id,
                    top_k=5,
                    user_id=user_id,
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

                # Stream the gap answer token by token
                for word in answer_text.split(" "):
                    yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                    await asyncio.sleep(0.02)

            else:
                # Emit sources BEFORE generation starts
                from backend.query.generator import build_citation_manifest
                _, citation_list = build_citation_manifest(chunks=verified.verified_chunks)
                citations_data = [c.model_dump() for c in citation_list]
                
                yield f"data: {json.dumps({'type': 'sources', 'sources': citations_data, 'request_id': request_id})}\n\n"

                # Generate grounded response
                yield f"data: {json.dumps({'type': 'status', 'status': 'Generating grounded response...', 'phase': 'generation', 'request_id': request_id})}\n\n"

                answer_text = ""
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
                grounding_score = verified.grounding_score

        # ── FULL_SWARM PATH ──
        elif route.tier in (ResponseTier.FULL_SWARM, ResponseTier.TOOL_EXEC):
            yield f"data: {json.dumps({'type': 'status', 'status': 'Initializing reasoning swarm...', 'phase': 'swarm', 'request_id': request_id})}\n\n"

            reasoning_orchestrator = ReasoningOrchestrator()
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

            if not answer_text:
                answer_text = "Reasoning completed but produced no output."

            yield f"data: {json.dumps({'type': 'status', 'status': f'Reasoning complete (confidence: {grounding_score:.0%})', 'phase': 'synthesis', 'request_id': request_id})}\n\n"

            # Stream the swarm answer
            words = answer_text.split(" ")
            for word in words:
                yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                await asyncio.sleep(0.015)

        # ── Run evaluations synchronously ──
        yield f"data: {json.dumps({'type': 'status', 'status': 'Running quality evaluations...', 'phase': 'evaluation', 'request_id': request_id})}\n\n"

        from backend.query.evaluators import evaluate_faithfulness, evaluate_relevance

        context_str = ""
        if route.tier == ResponseTier.FAST_RAG and 'verified' in locals() and hasattr(verified, 'verified_chunks'):
            context_str = "\n\n".join([c.content for c in verified.verified_chunks])
        elif route.tier == ResponseTier.FAST_RAG and 'gap_result' in locals():
            context_str = "\n\n".join([s.get("title", "") + ": " + s.get("url", "") for s in gap_result.get("sources", [])])

        faithfulness_score = 1.0
        relevance_score = 1.0
        eval_reasoning = ""

        with tracer.start_as_current_span("query.evaluation"):
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
                # Swarm / fallback
                relevance_res = await evaluate_relevance(question, answer_text)
                relevance_score = relevance_res["score"]
                faithfulness_score = grounding_score
                eval_reasoning = f"Faithfulness (confidence): {grounding_score:.2f}\n\nRelevance: {relevance_res['reasoning']}"

        # ── Emit metadata event ──
        yield f"data: {json.dumps({'type': 'metadata', 'grounding_score': grounding_score, 'intent': route.intent.value, 'tier': route.tier.value, 'request_id': request_id, 'faithfulness_score': faithfulness_score, 'relevance_score': relevance_score, 'eval_reasoning': eval_reasoning})}\n\n"

        # Calculate latency
        total_seconds = (datetime.utcnow() - start_ts).total_seconds()
        response_time_ms = int(total_seconds * 1000)

        # ── Persist to DB ──
        if answer_text and self.db is not None:
            try:
                with tracer.start_as_current_span("query.persistence"):
                    query_log = QueryLog(
                        workspace_id=workspace_id,
                        conversation_id=conversation_id,
                        question=question,
                        answer=answer_text,
                        sources=sources,
                        request_id=request_id,
                        faithfulness_score=faithfulness_score,
                        relevance_score=relevance_score,
                        eval_reasoning=eval_reasoning,
                        response_time_ms=response_time_ms,
                    )
                    self.db.add(query_log)
                    await self.cache.set_cache(
                        workspace_id, question, {"answer": answer_text, "sources": sources}
                    )
                    stmt = select(Conversation).where(Conversation.id == conversation_id)
                    result = await self.db.execute(stmt)
                    conv = result.scalar_one()
                    conv.updated_at = datetime.utcnow()
                    await self.db.commit()
            except Exception as e:
                logger.error("Failed to save query to database: %s", e)
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        # Record latency to Prometheus
        try:
            metrics.record_stream_latency(total_seconds, workspace_id=workspace_id)
        except Exception:
            pass

        yield f"data: {json.dumps({'type': 'done', 'request_id': request_id})}\n\n"
