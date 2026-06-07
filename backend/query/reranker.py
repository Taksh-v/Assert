import logging
import os
from typing import List, Dict, Any
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CrossEncoderReranker:
    """
    Second-stage reranker using FlashRank for CPU-optimized high precision.
    Requires no API keys and runs completely offline.
    """

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2"):
        self.model = None
        self.model_name = model_name

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Score and sort chunks based on the query using FlashRank.
        """
        if not chunks:
            return []

        if self.model is None:
            try:
                logger.info(f"Initializing FlashRank with model: {self.model_name}...")
                from flashrank import Ranker
                # Initialize local ranker (downloads small ONNX file to ~/.cache/flashrank on first run)
                self.model = Ranker(model_name=self.model_name)
            except Exception as e:
                logger.warning(f"FlashRank initialization failed: {e}. Using fallback scores.")
                for chunk in chunks:
                    chunk["cross_encoder_score"] = chunk.get("final_rank_score", chunk.get("score", 0.0))
                return sorted(chunks, key=lambda x: x["cross_encoder_score"], reverse=True)[:top_k]

        from flashrank import RerankRequest
        # Prepare passages for FlashRank (id must be unique/indexable)
        passages = []
        for i, chunk in enumerate(chunks):
            # Extract text from chunk
            text = chunk.get("text", "")
            if not text and "content" in chunk:
                text = chunk["content"]
            
            passages.append({
                "id": str(i),
                "text": text,
                "meta": chunk.get("metadata", {})
            })

        try:
            request = RerankRequest(query=query, passages=passages)
            results = self.model.rerank(request)
            
            scored_chunks = []
            for res in results:
                idx = int(res["id"])
                chunk = chunks[idx]
                chunk["cross_encoder_score"] = float(res["score"])
                scored_chunks.append(chunk)
                
            return scored_chunks[:top_k]
        except Exception as e:
            logger.error(f"FlashRank reranking execution failed: {e}")
            for chunk in chunks:
                chunk["cross_encoder_score"] = chunk.get("final_rank_score", chunk.get("score", 0.0))
            return sorted(chunks, key=lambda x: x["cross_encoder_score"], reverse=True)[:top_k]
