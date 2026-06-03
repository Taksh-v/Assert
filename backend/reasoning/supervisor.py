"""
Supervisor Agent — Dynamic Intent Classification and Routing.

Inspired by Mastra's Supervisor multi-agent pattern. Analyzes the user's
query intent and routes it to the most efficient reasoning flow,
saving tokens and latency for simple requests.
"""
import logging
import json
import re
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.generation.llm_client import LLMClient
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    QUICK_LOOKUP = "quick_lookup"      # Simple factual question, requires 1 retrieval
    DEEP_ANALYSIS = "deep_analysis"    # Complex multi-step reasoning required
    COMPARISON = "comparison"          # Cross-referencing multiple documents/entities
    ACTION_REQUEST = "action_request"  # Execution of a tool (e.g. "Create a Jira ticket")
    CONVERSATIONAL = "conversational"  # Chit-chat or simple clarification (no retrieval needed)


class IntentClassification(BaseModel):
    intent: QueryIntent
    reasoning: str = Field(description="Why this intent was selected")
    required_tools: list[str] = Field(default_factory=list, description="Any tools that seem explicitly requested")


class SupervisorAgent:
    """
    Acts as the main entry point for queries. Evaluates intent and
    decides which specialist agent/orchestrator should handle the request.
    """

    def __init__(self):
        self.client = LLMClient(model_type="smart")

    async def classify_intent(self, query: str) -> IntentClassification:
        """Analyze query to determine the best reasoning path."""
        # Fast-path heuristics to avoid LLM call if possible
        lower_query = query.lower().strip()
        if len(lower_query.split()) < 3 and "?" not in lower_query:
            if lower_query in ["hi", "hello", "thanks", "ok"]:
                return IntentClassification(
                    intent=QueryIntent.CONVERSATIONAL,
                    reasoning="Simple greeting or acknowledgment"
                )

        prompt = f"""Classify the intent of the following user query to route it to the correct AI specialist.

Intent Categories:
1. quick_lookup: A direct factual question that likely needs only one quick search (e.g., "What is our PTO policy?", "Who is the CEO?").
2. deep_analysis: A complex question requiring multi-step research and synthesis (e.g., "Why did our Q3 revenue drop?", "Design an architecture for X").
3. comparison: Explicitly asks to compare two or more things (e.g., "Compare React vs Vue based on our guidelines").
4. action_request: Asks the AI to DO something in an external system (e.g., "Create a GitHub issue", "Send a Slack message").
5. conversational: Chit-chat or follow-ups that don't need external knowledge (e.g., "Thanks", "Can you explain that more simply?").

Query: "{query}"

Output ONLY valid JSON matching this schema:
{{
  "intent": "quick_lookup|deep_analysis|comparison|action_request|conversational",
  "reasoning": "Brief explanation",
  "required_tools": ["github", "slack"] // only if explicitly requested, otherwise empty list
}}"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a highly efficient query router. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=settings.openrouter_smart_model,
                temperature=0
            )
            
            content = response.choices[0].message.content or ""
            
            # Try to load directly first
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Robust regex fallback to extract JSON block
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    raise ValueError("No JSON block found in LLM response")
            
            intent_str = data.get("intent", "quick_lookup")
            
            # Map string back to Enum safely
            try:
                intent_enum = QueryIntent(intent_str)
            except ValueError:
                intent_enum = QueryIntent.QUICK_LOOKUP
                
            return IntentClassification(
                intent=intent_enum,
                reasoning=data.get("reasoning", "Parsed from LLM"),
                required_tools=data.get("required_tools", [])
            )
            
        except Exception as e:
            logger.warning(f"Supervisor LLM classification failed: {e}. Defaulting to QUICK_LOOKUP.")
            return IntentClassification(
                intent=QueryIntent.QUICK_LOOKUP,
                reasoning=f"Error parsing LLM response: {e}"
            )

