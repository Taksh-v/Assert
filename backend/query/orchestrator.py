import logging
from typing import List, Dict, Any, Optional
from backend.core.vector_store import VectorStore
from backend.graph.graph_store import GraphStore
from backend.core.database import async_session
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)

class QueryOrchestrator:
    """
    Blueprint Layer 12: Retrieval Engine.
    Orchestrates Hybrid Search, Graph Expansion, and Reranking.
    """

    def __init__(self):
        self.vector_store = VectorStore()
        self.graph_store = GraphStore()
        # Layer 16: Agentic Memory Manager
        from backend.memory.manager import MemoryManager
        self.memory_manager = MemoryManager()
        
    async def retrieve(
        self, 
        query: str, 
        workspace_id: str, 
        user_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Execute the Elite Retrieval Pipeline.
        """
        logger.info(f"Executing Elite Retrieval for query: '{query}'")
        
        # Layer 16: Retrieve Agentic Context (User Preferences/Observations)
        agentic_context = await self.memory_manager.get_relevant_memories(
            workspace_id=workspace_id,
            query=query,
            user_id=user_id,
            limit=3
        )
        
        # 1. Semantic Search (Dense)
        from backend.ingestion.embedder import Embedder
        embedder = Embedder()
        query_vector = embedder.embed([query])[0]
        
        semantic_results = self.vector_store.search(
            workspace_id=workspace_id,
            query_vector=query_vector,
            top_k=top_k * 2,
            user_id=user_id,
            vector_name="content"
        )
        
        # 2. Keyword Search (BM25 via Postgres)
        keyword_results = await self._keyword_search(query, workspace_id, top_k * 2)
        
        # 3. Hybrid Fusion (RRF)
        fused_results = self.vector_store.reciprocal_rank_fusion(
            vector_results=semantic_results,
            keyword_results=keyword_results
        )
        
        # 4. Graph Context Expansion (Layer 10/12)
        expanded_results = await self._expand_with_graph(fused_results, query)
        
        # 5. Final Synthesis
        # Prepend Agentic Context if any
        if agentic_context:
            memory_blocks = [
                {
                    "chunk_id": f"memory_{i}",
                    "text": f"[Agentic Memory]: {m['content']}",
                    "score": 0.9,
                    "metadata": {"type": "agentic_memory"}
                }
                for i, m in enumerate(agentic_context)
            ]
            expanded_results = memory_blocks + expanded_results

        final_results = expanded_results[:top_k + len(agentic_context)]
        
        logger.info(f"Retrieved {len(final_results)} blocks (incl. {len(agentic_context)} memories).")
        return final_results

    async def _keyword_search(self, query: str, workspace_id: str, limit: int) -> List[Dict[str, Any]]:
        """Perform Postgres Full-Text Search (BM25 equivalent)."""
        async with async_session() as session:
            # Layer 15 Fix: Only fetch ACTIVE chunks
            sql = text("""
                SELECT id, content, metadata_json, ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', :query)) as rank
                FROM chunks
                WHERE workspace_id = :ws_id
                AND is_active = TRUE
                AND to_tsvector('english', content) @@ plainto_tsquery('english', :query)
                ORDER BY rank DESC
                LIMIT :limit
            """)
            result = await session.execute(sql, {"query": query, "ws_id": workspace_id, "limit": limit})
            rows = result.fetchall()
            
            return [
                {
                    "chunk_id": row.id,
                    "text": row.content,
                    "score": float(row.rank),
                    "metadata": row.metadata_json
                }
                for row in rows
            ]

    async def _expand_with_graph(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Use the Graph Store to find related context that semantic search might have missed.
        """
        # Heuristic: If we find a 'Project' or 'Employee' in the results, 
        # pull related items from the graph.
        if not self.graph_store:
            return results
            
        entities_to_check = set()
        for res in results[:3]: # Only check top 3 for speed
            meta = res.get("metadata", {})
            entities = meta.get("extracted_entities", [])
            entities_to_check.update(entities)
            
        if not entities_to_check:
            return results
            
        graph_context = []
        for entity in list(entities_to_check)[:2]:
            cluster = self.graph_store.get_knowledge_cluster(entity)
            if cluster and cluster.get("relationships"):
                # Formulate a context string from the graph
                rels = [f"{r['rel']} -> {r['name']} ({r['type'][0] if r['type'] else 'Unknown'})" 
                        for r in cluster["relationships"]]
                graph_context.append({
                    "chunk_id": f"graph_{entity}",
                    "text": f"[Graph Context for {entity}]: " + ", ".join(rels),
                    "score": 0.8, # Artificial score for RRF position
                    "metadata": {"type": "graph_expansion", "entity": entity}
                })
        
        # Prepend graph context to search results
        return graph_context + results
