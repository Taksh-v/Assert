import logging
from typing import Dict, Any, List, Optional
from backend.agent.router import QueryRouter
from backend.query.retriever import Retriever
from backend.query.generator import Generator
from backend.agent.tools.github import GithubTool

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Main entry point for agentic interactions.
    Coordinates between routing, retrieval, and tool usage.
    """

    def __init__(self):
        self.router = QueryRouter()
        self.retriever = Retriever()
        self.generator = Generator()

    async def process_query(self, query: str, workspace_id: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process a user query using the agentic pipeline.
        """
        logger.info(f"Agent processing query: {query}")
        
        # 1. Route the query
        decision = await self.router.route(query)
        logger.info(f"Routing Decision: {decision.intent} ({decision.reasoning})")
        
        # 2. Execute based on decision
        if decision.intent == "tool_call" and decision.tool_name == "github":
            # Direct Tool Execution (Layer 1 - Master Blueprint)
            # This is "Precision Engine" logic: skip RAG if tool is better
            token = config.get("github_token") if config else None
            if token:
                gh = GithubTool(token)
                # Hardcoded logic for now, in production use LLM to choose method
                repo = config.get("github_repo", "Taksh-v/Assest")
                data = gh.get_latest_commits(repo)
                return {
                    "answer": f"Here are the latest commits for {repo}:",
                    "data": data,
                    "type": "tool_response"
                }
        
        # 3. Default to Knowledge Retrieval (RAG)
        chunks = await self.retriever.search(query, workspace_id)
        answer = await self.generator.generate_answer(query, chunks)
        
        return {
            "answer": answer.answer_text,
            "sources": [s.dict() for s in answer.sources],
            "type": "knowledge_response"
        }
