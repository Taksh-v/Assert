import logging
import os
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CrossEncoderReranker:
    """
    Second-stage reranker using a Cross-Encoder for high precision.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = None
        self.model_name = model_name

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Score and sort chunks based on the query.
        """
        if not chunks:
            return []

        if self.model is None:
            if settings.is_development and not os.environ.get("ASSEST_LOAD_LOCAL_MODELS"):
                for chunk in chunks:
                    chunk["cross_encoder_score"] = chunk.get("final_rank_score", chunk.get("score", 0.0))
                return sorted(chunks, key=lambda x: x["cross_encoder_score"], reverse=True)[:top_k]

            try:
                logger.info(f"Loading Cross-Encoder model: {self.model_name}...")
                self.model = CrossEncoder(self.model_name, local_files_only=True)
            except Exception as e:
                logger.warning(f"Cross-Encoder unavailable, using existing rank scores: {e}")
                for chunk in chunks:
                    chunk["cross_encoder_score"] = chunk.get("final_rank_score", chunk.get("score", 0.0))
                return sorted(chunks, key=lambda x: x["cross_encoder_score"], reverse=True)[:top_k]

        # Prepare pairs: (query, text)
        pairs = [[query, chunk["text"]] for chunk in chunks]
        
        # Compute scores
        scores = self.model.predict(pairs)
        
        # Attach scores to chunks
        for chunk, score in zip(chunks, scores):
            chunk["cross_encoder_score"] = float(score)
            
        # Sort by score
        reranked = sorted(chunks, key=lambda x: x["cross_encoder_score"], reverse=True)
        
        return reranked[:top_k]
