import logging
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel
from groq import Groq
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RoutingDecision(BaseModel):
    intent: Literal["knowledge_retrieval", "tool_call", "general_chat"]
    tool_name: Optional[str] = None
    reasoning: str


class QueryRouter:
    """
    Routes incoming queries to the appropriate engine.
    """

    def __init__(self):
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = "llama3-70b-8192"

    async def route(self, query: str) -> RoutingDecision:
        """
        Classify the intent of the user query.
        """
        prompt = f"""
        You are the Routing Engine for Assest, an Enterprise AI.
        Your job is to decide if a query needs:
        1. 'knowledge_retrieval': Searching internal docs (Notion, Drive, etc).
        2. 'tool_call': Performing an action or fetching real-time data from an API (GitHub, Jira).
        3. 'general_chat': Greeting or general conversation.

        Available Tools:
        - github: For repo issues, commits, or PRs.
        - jira: For project tickets and sprints.
        
        Query: "{query}"

        Return JSON only:
        {{
            "intent": "knowledge_retrieval" | "tool_call" | "general_chat",
            "tool_name": "github" | "jira" | null,
            "reasoning": "brief explanation"
        }}
        """
        
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[{{"role": "user", "content": prompt}}],
                model=self.model,
                response_format={{"type": "json_object"}}
            )
            return RoutingDecision.model_validate_json(chat_completion.choices[0].message.content)
        except Exception as e:
            logger.error(f"Routing failed: {e}")
            return RoutingDecision(intent="knowledge_retrieval", reasoning="Fallback due to error")
