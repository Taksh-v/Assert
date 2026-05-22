import logging
from typing import List, Dict, Any, Optional
from backend.core.config import get_settings
from backend.ingestion.embedder import Embedder
from backend.core.vector_store import VectorStore
from backend.core.llm_client import LLMClient

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
        prompt = f"""
        Classify the intent of this question for a knowledge base search.
        
        1. Scope: 'broad' (general topic) or 'specific' (particular fact).
        2. Temporal: 'latest' (user wants newest), 'historical' (user wants old/all), or 'none'.
        
        Question: {question}
        
        Return ONLY valid JSON:
        {{"scope": "broad|specific", "temporal": "latest|historical|none"}}
        """
        try:
            res = await self.llm.chat_completion("You are a search intent classifier.", prompt)
            if "```json" in res:
                res = res.split("```json")[1].split("```")[0].strip()
            elif "```" in res:
                res = res.split("```")[1].split("```")[0].strip()
            
            import json
            data = json.loads(res)
            return {
                "scope": data.get("scope", "specific"),
                "temporal": data.get("temporal", "none")
            }
        except Exception:
            return {"scope": "specific", "temporal": "none"}

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
        try:
            return await self.llm.chat_completion("You are a helpful document simulator.", prompt)
        except Exception:
            return question

    async def search(self, question: str, workspace_id: str, top_k: int = 5, user_id: Optional[str] = None) -> List[RetrievalResult]:
        """
        Perform hybrid + graph search, rerank, and return top results.
        """
        logger.info(f"Augmented temporal searching for: {question}")
        
        # 1. Intent Detection (Scope + Temporal)
        intent_data = await self._detect_intent(question)
        scope = intent_data["scope"]
        temporal = intent_data["temporal"]
        
        vector_target = "title" if scope == "broad" else "content"
        logger.info(f"Intent detected: {scope}, Temporal: {temporal} (Targeting: {vector_target})")
        
        # 2. Graph Search (Relationships - Layer 10)
        graph_context = []
        try:
            potential_entities = [w for w in question.split() if w[0].isupper()]
            for ent in potential_entities:
                related = self.graph_store.get_context(ent).get("relationships", [])
                if related:
                    graph_context.extend(related)
        except Exception as ge:
            logger.warning(f"Graph retrieval failed: {ge}")
        
        # 3. HyDE (Hypothetical Document Embedding - Layer 12)
        hyde_answer = await self._generate_hyde_answer(question)
        logger.info(f"Generated HyDE context for query expansion")
        
        # 4. Vector Search (Semantic)
        question_embedding = self.embedder.embed([hyde_answer])[0]
        vector_results = self.vector_store.search(
            workspace_id=workspace_id,
            query_vector=question_embedding,
            top_k=top_k * 2, # Get more for fusion
            user_id=user_id,
            vector_name=vector_target
        )
        
        # 5. Keyword Search (BM25 style via Postgres)
        keyword_results = []
        async with async_session() as session:
            keywords = question.split()
            filters = [DBChunk.content.ilike(f"%{kw}%") for kw in keywords if len(kw) > 3]
            
            if filters:
                stmt = select(DBChunk).where(
                    DBChunk.workspace_id == workspace_id,
                    or_(*filters)
                ).limit(20)
                res = await session.execute(stmt)
                db_chunks = res.scalars().all()
                
                keyword_results = [
                    {
                        "chunk_id": c.id,
                        "text": c.content,
                        "metadata": {
                            "title": c.document_title,
                            "source_url": c.source_url,
                            "content_tier": c.tier,
                            "source_modified_at": c.source_modified_at.isoformat() if c.source_modified_at else None,
                            "heading_path": c.heading_path or []
                        }
                    }
                    for c in db_chunks
                ]

        # 6. Reciprocal Rank Fusion (RRF)
        combined_results = self.vector_store.reciprocal_rank_fusion(
            vector_results=vector_results,
            keyword_results=keyword_results
        )
        
        # 7. Multi-Signal Reranking (Metadata, Tier, Recency Boosted)
        # The Ranker will now automatically use the temporal metadata
        multi_signal_results = self.ranker.rerank(combined_results, question, top_k=15)
        
        # 8. Cross-Encoder Reranking (Final decision)
        if self.reranker:
            final_ranked = self.reranker.rerank(question, multi_signal_results, top_k=top_k)
        else:
            final_ranked = multi_signal_results[:top_k]
        
        # 9. Map to RetrievalResult
        return [
            RetrievalResult(
                chunk_id=res.get("chunk_id", "unknown"),
                content=res.get("text", ""),
                source_url=res.get("metadata", {}).get("source_url", ""),
                title=res.get("metadata", {}).get("title", "Untitled"),
                score=res.get("cross_encoder_score", res.get("final_rank_score", res.get("score", 0.0))),
                metadata=res.get("metadata", {})
            )
            for res in final_ranked
        ]
