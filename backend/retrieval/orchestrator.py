import logging
from typing import List, Dict, Any, Optional
from backend.retrieval.query_analyzer import QueryAnalyzer, RetrievalPlan
from backend.retrieval.temporal_engine import TemporalEngine
from backend.retrieval.graph_expansion import GraphExpansionEngine
from backend.retrieval.context_assembler import ContextAssembler
from backend.query.retriever import Retriever
from backend.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

class RetrievalOrchestrator:
    """
    Phase 2: Retrieval Intelligence Layer.
    Orchestrates the advanced multi-stream retrieval pipeline.
    """

    def __init__(self):
        self.analyzer = QueryAnalyzer()
        self.retriever = Retriever() # Standard vector/BM25 retriever
        self.graph_engine = GraphExpansionEngine()
        self.temporal_engine = TemporalEngine()
        self.assembler = ContextAssembler()
        self.memory_manager = MemoryManager()

    async def retrieve_reasoning_context(
        self, 
        query: str, 
        workspace_id: str, 
        user_id: Optional[str] = None
    ) -> str:
        """
        Execute the full Phase 2 retrieval intelligence loop.
        """
        logger.info(f"Phase 2 Retrieval: '{query}'")
        
        # 1. Query Understanding (Intent & Planning)
        plan: RetrievalPlan = await self.analyzer.analyze(query)
        logger.info(f"Retrieval Plan: {plan.intent} | Entities: {plan.entities}")
        
        # 2. Parallel Retrieval Streams
        
        # A. Vector Retrieval (Semantic + Keyword)
        # We use the tasks from the decomposition if available
        search_query = plan.tasks[0] if plan.tasks else query
        retrieved_objects = await self.retriever.search(
            question=search_query,
            workspace_id=workspace_id,
            top_k=10
        )
        vector_results = [
            {
                "chunk_id": r.chunk_id,
                "text": r.content,
                "score": r.score,
                "metadata": {
                    **r.metadata,
                    "title": r.title,
                    "source_url": r.source_url
                }
            }
            for r in retrieved_objects
        ]
        
        # B. Graph Expansion
        graph_results = []
        if plan.requires_graph:
            graph_results = await self.graph_engine.expand(plan.entities)
            
        # C. Temporal Retrieval
        event_results = []
        if plan.requires_temporal or plan.intent in ["root_cause", "temporal"]:
            event_results = await self.temporal_engine.get_relevant_events(
                workspace_id=workspace_id,
                entities=plan.entities
            )
            
        # D. Agentic Memory (Context Window)
        memory_context = await self.memory_manager.get_context_window(
            workspace_id=workspace_id,
            working_messages=[{"role": "user", "content": query}],
            user_id=user_id
        )
        
        # 3. Context Assembly & Reranking
        final_context = self.assembler.assemble(
            query=query,
            vector_results=vector_results,
            graph_results=graph_results,
            event_results=event_results,
            agentic_memory=[{"text": memory_context}] if memory_context else []
        )
        
        return final_context
