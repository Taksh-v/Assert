import logging
from typing import Dict, Any, List, Optional
from backend.agent.router import QueryRouter
from backend.query.retriever import Retriever
from backend.query.generator import Generator
from backend.agent.tools.github import GithubTool
from backend.agent.tools.wren import WrenAITool
from backend.agent.memory import MemoryManager

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Main entry point for agentic interactions.
    Coordinates between routing, retrieval, analytical engine, tools, and memory.
    """

    def __init__(self):
        self.router = QueryRouter()
        self.retriever = Retriever()
        self.generator = Generator()
        self.wren = WrenAITool()
        self.memory = MemoryManager()

    async def process_query(self, query: str, workspace_id: str, user_id: str = "default_user", config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process a user query using the agentic pipeline with conversational memory.
        """
        logger.info(f"Agent processing query for {user_id}: {query}")
        
        # 0. Fetch Short-Term Memory
        user_mem = await self.memory.get_memory(user_id, workspace_id)
        context_summary = user_mem.recent_context_summary if user_mem else ""
        
        # 1. Route the query (Inject memory into prompt if needed)
        # For routing, we mostly focus on the current intent
        decision = await self.router.route(query)
        logger.info(f"Routing Decision: {decision.intent}")
        
        # 2. Analytical Intelligence (Logical Brain)
        analytical_triggers = ["how many", "count", "average", "total", "sum", "list all"]
        if any(trigger in query.lower() for trigger in analytical_triggers):
            res = await self.wren.ask_data(query)
            if res["status"] == "success":
                return {"answer": res["answer"], "data": res["results"], "type": "analytical_response"}
        
        # 3. Knowledge Retrieval (RAG) with Temporal/Memory Context
        # We append the context summary to the search to improve relevance
        search_query = f"{context_summary}\n{query}" if context_summary else query
        chunks = await self.retriever.search(search_query, workspace_id, user_id=user_id)
        
        # 4. Generate Answer (Pass summary to generator)
        answer = await self.generator.generate_answer(f"Context: {context_summary}\nQuestion: {query}", chunks)
        
        # 5. Post-Process: Update Memory in background
        interaction_text = f"User asked: {query}\nBrain answered: {answer.answer_text}"
        import asyncio
        asyncio.create_task(self.memory.summarize_episode(user_id, workspace_id, interaction_text))
        
        return {
            "answer": answer.answer_text,
            "sources": [s for s in answer.sources],
            "type": "knowledge_response"
        }
