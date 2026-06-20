import logging
from typing import List, Dict, Any, Optional
from backend.core.config import get_settings
from backend.ingestion.embedder import Embedder
from backend.core.vector_store import VectorStore
from backend.core.llm_client import LLMClient
from backend.observability.telemetry import tracer

from backend.core.database import async_session
from sqlalchemy import select, or_
from backend.models.chunk import Chunk as DBChunk
from backend.core.ranker import Ranker
from backend.query.reranker import CrossEncoderReranker
from backend.graph.graph_store import GraphStore

settings = get_settings()
logger = logging.getLogger(__name__)


class RetrievalResult:
    def __init__(self, chunk_id: str, content: str, source_url: str, title: str, score: float, metadata: Dict[str, Any] = None):
        self.chunk_id = chunk_id
        self.content = content
        self.source_url = source_url
        self.title = title
        self.score = score
        self.metadata = metadata or {}


class Retriever:
    """
    Retrieves relevant knowledge chunks using hybrid search (Vector + BM25).
    Incorporates Temporal Intent Detection and HyDE for organizational superintelligence.
    """

    def __init__(self):
        self.embedder = Embedder()
        self.vector_store = VectorStore()
        self.ranker = Ranker()
        self.reranker = CrossEncoderReranker() if settings.enable_reranking else None
        self.graph_store = GraphStore()
        self.llm = LLMClient(model_type="fast")

    async def _detect_intent(self, question: str) -> Dict[str, str]:
        """Classify search intent including temporal requirements."""
        lower = question.lower().strip()
        words = lower.split()

        broad_markers = (
            "overview",
            "summarize",
            "summary",
            "explain",
            "compare",
            "difference",
            "tradeoff",
            "architecture",
            "design",
            "strategy",
        )
        temporal_markers = (
            "latest",
            "recent",
            "current",
            "today",
            "this week",
            "this month",
            "newest",
        )
        historical_markers = (
            "historical",
            "previous",
            "old",
            "last year",
            "past",
            "earlier",
            "ever",
            "all time",
        )

        with tracer.start_as_current_span("retrieval.intent") as span:
            span.set_attribute("question", question[:200])

            temporal = "none"
            if any(marker in lower for marker in temporal_markers):
                temporal = "latest"
            elif any(marker in lower for marker in historical_markers):
                temporal = "historical"

            scope = "specific"
            if len(words) >= 12 or any(marker in lower for marker in broad_markers):
                scope = "broad"
            elif lower.startswith(("who is", "what is", "where is", "when is", "what are", "how many")):
                scope = "specific"

            span.set_attribute("scope", scope)
            span.set_attribute("temporal", temporal)
            return {"scope": scope, "temporal": temporal}

    async def _generate_hyde_answer(self, question: str) -> str:
        """
        Generate a hypothetical answer to expand the query (HyDE).
        Uses the local $0 brain gateway.
        """
        prompt = f"""
        Write a brief, factual paragraph that answers the following question. 
        Don't worry about being correct, just sound like a document that contains the answer.
        
        Question: {question}
        
        Hypothetical Answer:
        """
        with tracer.start_as_current_span("retrieval.hyde") as span:
            span.set_attribute("question", question[:200])
            try:
                result = await self.llm.chat_completion(
                    "You are a helpful document simulator.",
                    prompt,
                    max_tokens=96,
                    prompt_cache_key="hyde:v1",
                )
                span.set_attribute("hyde_length", len(result))
                return result
            except Exception as e:
                span.record_exception(e)
                return question

    async def search(self, question: str, workspace_id: str, top_k: int = 5, user_id: Optional[str] = None, user_role: Optional[str] = "employee", context_files: Optional[List[str]] = None) -> List[RetrievalResult]:
        """
        Perform hybrid + graph search, rerank, and return top results.
        """
        logger.info(f"Augmented temporal searching for: {question} with role {user_role}")
        with tracer.start_as_current_span("retrieval.search") as span:
            span.set_attribute("workspace_id", workspace_id)
            span.set_attribute("top_k", top_k)
            span.set_attribute("user_id", user_id or "")
            span.set_attribute("user_role", user_role or "")
        
            # 1. Intent Detection (Scope + Temporal)
            intent_data = await self._detect_intent(question)
            scope = intent_data["scope"]
            temporal = intent_data["temporal"]
        
            vector_target = "title" if scope == "broad" else "content"
            logger.info(f"Intent detected: {scope}, Temporal: {temporal} (Targeting: {vector_target})")

            # 2. Graph Search (Relationships - Layer 10)
            graph_context = []
            if settings.enable_graph_retrieval and any(w[:1].isupper() for w in question.split()):
                try:
                    potential_entities = [w for w in question.split() if w[:1].isupper()]
                    for ent in potential_entities[:4]:
                        cluster = await self.graph_store.async_get_context(ent)
                        related = cluster.get("relationships", [])
                        if related:
                            graph_context.extend(related)
                    span.set_attribute("graph_context_count", len(graph_context))
                except Exception as ge:
                    logger.warning(f"Graph retrieval failed: {ge}")
                    span.record_exception(ge)

            # 3. HyDE (Hypothetical Document Embedding - Layer 12)
            words = question.lower().strip().split()
            if settings.enable_hyde and scope == "broad" and len(words) >= settings.hyde_min_query_words:
                hyde_answer = await self._generate_hyde_answer(question)
                logger.info("Generated HyDE context for query expansion")
            else:
                hyde_answer = question

            # 4. Vector Search (Semantic) — use async embedder to avoid blocking
            with tracer.start_as_current_span("retrieval.vector_search") as vspan:
                question_embedding = (await self.embedder.aembed([hyde_answer]))[0]
                search_kwargs = {
                    "workspace_id": workspace_id,
                    "query_vector": question_embedding,
                    "top_k": top_k * 2, # Get more for fusion
                    "user_id": user_id,
                    "vector_name": vector_target,
                }
                if context_files is not None:
                    search_kwargs["filter_titles"] = context_files
                vector_results = await self.vector_store.async_search(**search_kwargs)
                if context_files:
                    for res in vector_results:
                        if "metadata" not in res:
                            res["metadata"] = {}
                        res["metadata"]["is_context_file"] = True
                vspan.set_attribute("vector_results_count", len(vector_results))

            # 5. Keyword Search (In-Memory BM25 Indexer)
            keyword_results = []
            
            # Context Files Explicit Fetch
            if context_files:
                async with async_session() as session:
                    context_stmt = select(DBChunk).where(
                        DBChunk.workspace_id == workspace_id,
                        DBChunk.document_title.in_(context_files)
                    ).limit(30)
                    context_res = await session.execute(context_stmt)
                    context_chunks = context_res.scalars().all()
                    for c in context_chunks:
                        keyword_results.append({
                            "chunk_id": c.id,
                            "text": c.content,
                            "score": 10.0, # High base score to ensure it bypasses threshold
                            "metadata": {
                                "title": c.document_title,
                                "source_url": c.source_url,
                                "content_tier": c.tier,
                                "source_modified_at": c.source_modified_at.isoformat() if c.source_modified_at else None,
                                "heading_path": c.heading_path or [],
                                "is_context_file": True,
                                "parent_id": c.parent_id
                            }
                        })

            # Fetch filtered chunk IDs for sparse indexer when context_files is present
            filter_chunk_ids = None
            if context_files:
                async with async_session() as session:
                    stmt = select(DBChunk.id).where(
                        DBChunk.workspace_id == workspace_id,
                        DBChunk.document_title.in_(context_files)
                    )
                    res = await session.execute(stmt)
                    filter_chunk_ids = []
                    for row in res.all():
                        if hasattr(row, "_mapping"):
                            filter_chunk_ids.append(row._mapping["id"])
                        elif isinstance(row, tuple):
                            filter_chunk_ids.append(row[0])
                        elif hasattr(row, "id"):
                            filter_chunk_ids.append(row.id)
                        else:
                            filter_chunk_ids.append(row)

            # BM25 Search
            from backend.query.sparse_indexer import get_sparse_indexer
            sparse_indexer = get_sparse_indexer()
            bm25_hits = sparse_indexer.search(question, top_k=top_k * 2, filter_ids=filter_chunk_ids)
            keyword_chunk_ids = [hit["chunk_id"] for hit in bm25_hits]
            
            if keyword_chunk_ids:
                async with async_session() as session:
                    stmt = select(DBChunk).where(
                        DBChunk.id.in_(keyword_chunk_ids),
                        DBChunk.workspace_id == workspace_id
                    )
                    res = await session.execute(stmt)
                    db_chunks = res.scalars().all()
                    
                    score_map = {hit["chunk_id"]: hit["score"] for hit in bm25_hits}
                    fetched_ids = {item["chunk_id"] for item in keyword_results}
                    for c in db_chunks:
                        # Prevent duplicate insertion if it was already fetched
                        if c.id in fetched_ids:
                            continue
                        is_ctx = context_files and c.document_title in context_files
                        keyword_results.append({
                            "chunk_id": c.id,
                            "text": c.content,
                            "score": score_map.get(c.id, 0.0),
                            "metadata": {
                                "title": c.document_title,
                                "source_url": c.source_url,
                                "content_tier": c.tier,
                                "source_modified_at": c.source_modified_at.isoformat() if c.source_modified_at else None,
                                "heading_path": c.heading_path or [],
                                "is_context_file": is_ctx,
                                "parent_id": c.parent_id
                            }
                        })
                    
                    # Sort keyword_results by score descending to preserve ranking order for RRF
                    keyword_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
            
            span.set_attribute("keyword_results_count", len(keyword_results))

            # 6. Reciprocal Rank Fusion (RRF)
            from backend.retrieval.fusion import reciprocal_rank_fusion
            combined_results = reciprocal_rank_fusion(vector_results=vector_results, keyword_results=keyword_results)
            
            # Post-filter results for permissions and roles at retrieval layer
            from backend.retrieval.security import apply_security_filter
            combined_results = apply_security_filter(
                combined_results, 
                user_id, 
                settings.is_development, 
                user_role=user_role
            )

            # 7. Multi-Signal Reranking (Metadata, Tier, Recency Boosted)
            # The Ranker will now automatically use the temporal metadata
            # Prune candidates to N=8 to optimize CPU FlashRank reranking latency
            multi_signal_results = self.ranker.rerank(combined_results, question, top_k=8)
        
            # 8. Cross-Encoder Reranking (Final decision)
            if self.reranker:
                final_ranked = self.reranker.rerank(question, multi_signal_results, top_k=top_k)
            else:
                final_ranked = multi_signal_results[:top_k]
                
            # Apply truth resolution to adjust scores based on source authority and filter low-trust chunks
            from backend.query.truth_resolver import TruthResolver
            final_ranked = TruthResolver.resolve_weights(final_ranked)
            
            span.set_attribute("final_results_count", len(final_ranked))

            # 8.5. Map matched child chunks back to parent chunks if parent_id exists
            parent_ids_to_fetch = []
            for res in final_ranked:
                parent_id = res.get("metadata", {}).get("parent_id")
                if parent_id:
                    parent_ids_to_fetch.append(parent_id)

            parent_chunks_map = {}
            if parent_ids_to_fetch:
                async with async_session() as session:
                    stmt = select(DBChunk.id, DBChunk.content).where(DBChunk.id.in_(parent_ids_to_fetch))
                    res = await session.execute(stmt)
                    parent_db_chunks = res.all()
                    for row in parent_db_chunks:
                        if hasattr(row, "_mapping"):
                            p_id = row._mapping["id"]
                            p_content = row._mapping["content"]
                        elif isinstance(row, tuple):
                            p_id, p_content = row
                        elif hasattr(row, "id") and hasattr(row, "content"):
                            p_id = row.id
                            p_content = row.content
                        else:
                            p_id, p_content = row
                        parent_chunks_map[p_id] = p_content
        
            # 9. Map to RetrievalResult
            results = []
            for res in final_ranked:
                parent_id = res.get("metadata", {}).get("parent_id")
                content = res.get("text", "")
                if parent_id and parent_id in parent_chunks_map:
                    content = parent_chunks_map[parent_id]
                
                results.append(
                    RetrievalResult(
                        chunk_id=res.get("chunk_id", "unknown"),
                        content=content,
                        source_url=res.get("metadata", {}).get("source_url", ""),
                        title=res.get("metadata", {}).get("title", "Untitled"),
                        score=res.get("cross_encoder_score", res.get("final_rank_score", res.get("score", 0.0))),
                        metadata=res.get("metadata", {})
                    )
                )
            return results
