import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class Ranker:
    """
    Reranks retrieved chunks based on multiple signals:
    - Semantic Similarity
    - Keyword Match
    - Content Tier
    - Recency
    - Quality Score
    """

    @staticmethod
    def compute_rank_score(chunk_data: Dict[str, Any], query: str) -> float:
        """
        Compute a composite score for a chunk.
        """
        # 1. Semantic Score (from Qdrant)
        # weight: 0.35
        semantic_score = chunk_data.get("score", 0.5) * 0.35
        
        # 2. Keyword/RRF Score
        # weight: 0.20
        rrf_score = chunk_data.get("rrf_score", 0.02) * 0.20
        
        # 3. Content Tier (Tier 1 is highest)
        # weight: 0.20
        tier = chunk_data.get("metadata", {}).get("content_tier", 2)
        tier_map = {1: 1.0, 2: 0.6, 3: 0.3}
        tier_score = tier_map.get(tier, 0.5) * 0.20
        
        # 4. Recency (Smarter Temporal Decay - Phase 4)
        # weight: 0.25 (Upped from 0.20 to make Time a primary dimension of truth)
        recency_score = 0.5
        modified_at_str = chunk_data.get("metadata", {}).get("source_modified_at") or chunk_data.get("metadata", {}).get("created_at")
        
        if modified_at_str:
            try:
                # Handle various ISO formats
                clean_ts = modified_at_str.replace("Z", "+00:00")
                modified_at = datetime.fromisoformat(clean_ts).replace(tzinfo=None)
                days_old = max(0, (datetime.utcnow() - modified_at).days)
                
                import math
                # Aggressive decay for the first year, then slow decay
                # e^(-0.01 * days) -> 50% score after ~70 days
                recency_score = math.exp(-0.01 * days_old)
                
                # 'Newness Boost': If it's from the last 7 days, it gets a flat 1.0 multiplier
                if days_old <= 7:
                    recency_score = 1.0
                elif days_old <= 30:
                    recency_score = max(recency_score, 0.9)
            except Exception:
                recency_score = 0.5 # Default for missing dates
        
        recency_score *= 0.25 # New weight
        
        # 5. Structural Context Boost (Phase 3)
        # weight: 0.10
        # Boost chunks that belong to a clear heading hierarchy (Breadcrumbs from Phase 2)
        heading_path = chunk_data.get("metadata", {}).get("heading_path", [])
        structure_score = min(1.0, len(heading_path) * 0.3) * 0.10
        
        # 6. Quality Score
        quality = chunk_data.get("metadata", {}).get("quality_score", 0.5)
        quality_score = quality * 0.05
        
        return semantic_score + rrf_score + tier_score + recency_score + structure_score + quality_score

    def rerank(self, chunks: List[Dict[str, Any]], query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        """
        Rerank a list of chunks and return the top K.
        """
        for chunk in chunks:
            chunk["final_rank_score"] = self.compute_rank_score(chunk, query)
            
        # Sort by final score
        ranked_chunks = sorted(chunks, key=lambda x: x["final_rank_score"], reverse=True)
        
        return ranked_chunks[:top_k]
