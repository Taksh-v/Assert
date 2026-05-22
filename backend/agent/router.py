import logging
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RoutingDecision(BaseModel):
    intent: Literal["knowledge_retrieval", "tool_call", "general_chat"]
    tool_name: Optional[str] = None
    reasoning: str


from backend.core.llm_client import LLMClient

class QueryRouter:
    """
    Routes incoming queries to the appropriate engine using the local brain proxy.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    async def route(self, query: str) -> RoutingDecision:
        """
        Classify the intent of the user query.
        """
        prompt = f"""
        You are the Routing Engine for Assest, an Enterprise AI.
        Decide if a query needs:
        1. 'knowledge_retrieval': Searching internal docs (Notion, Drive, etc).
        2. 'tool_call': Fetching real-time data from an API (GitHub, Jira).
        3. 'general_chat': Greeting or general conversation.

        Available Tools:
        - github: Repo issues, commits, PRs.
        - jira: Project tickets, sprints.

        Query: "{query}"

        Return ONLY valid JSON:
        {{
            "intent": "knowledge_retrieval" | "tool_call" | "general_chat",
            "tool_name": "github" | "jira" | null,
            "reasoning": "brief explanation"
        }}
        """

        try:
            res = await self.llm.chat_completion("You are a specialized enterprise query router.", prompt)
            # Basic JSON extraction
            if "```json" in res:
                res = res.split("```json")[1].split("```")[0].strip()
            elif "```" in res:
                res = res.split("```")[1].split("```")[0].strip()

            return RoutingDecision.model_validate_json(res)
        except Exception as e:
            logger.error(f"Routing failed: {e}")
            return RoutingDecision(intent="knowledge_retrieval", reasoning="Fallback due to error")

