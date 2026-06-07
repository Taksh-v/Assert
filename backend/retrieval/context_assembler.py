import logging
from typing import List, Dict, Any
from backend.query.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)

class ContextAssembler:
    """
    Layer 12: Context Assembly & Reranking.
    Synthesizes multiple retrieval streams into a coherent reasoning block.
    """

    def __init__(self):
        self.reranker = CrossEncoderReranker()

    def assemble(
        self, 
        query: str,
        vector_results: List[Dict[str, Any]], 
        graph_results: List[Dict[str, Any]], 
        event_results: List[Dict[str, Any]],
        agentic_memory: List[Dict[str, Any]] = []
    ) -> str:
        """
        Combine all results and build the final context string.
        """
        # 1. Rerank vector results for precision
        ranked_vector = self.reranker.rerank(query, vector_results)
        
        # 2. Build segments
        segments = []
        
        if agentic_memory:
            segments.append("## USER MEMORY & PREFERENCES\n" + "\n".join([m['text'] for m in agentic_memory]))
            
        if event_results:
            segments.append("## ORGANIZATIONAL TIMELINE (EVENTS)\n" + "\n".join([e['text'] if 'text' in e else f"[{e['timestamp']}] {e['type']}: {e['title']}" for e in event_results]))
            
        if graph_results:
            segments.append("## KNOWLEDGE GRAPH FACTS\n" + "\n".join([g['text'] for g in graph_results]))
            
        if ranked_vector:
            segments.append("## DOCUMENTATION & LOGS\n" + "\n".join([f"--- SOURCE: {r.get('metadata', {}).get('title', 'Unknown')} ---\n{r['text']}" for r in ranked_vector]))
            
        return "\n\n".join(segments)
