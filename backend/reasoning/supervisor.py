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
    LLM-based intent classifier for non-trivial queries.

    Called ONLY by AdaptiveRouter after its own heuristics have been
    exhausted, so this class intentionally does NOT duplicate heuristic
    checks (greetings, action verbs, factual prefixes, comparison tokens).
    """

    def __init__(self):
        self.client = LLMClient(model_type="fast")

    async def classify_intent(self, query: str) -> IntentClassification:
        """Classify query intent via LLM. Heuristics live in AdaptiveRouter."""

        prompt = f"""Classify this query's intent. Pick ONE category:
- quick_lookup: simple factual question (1 search needed)
- deep_analysis: complex, multi-step research required
- comparison: explicitly comparing 2+ things
- action_request: user wants an external action performed
- conversational: chit-chat, follow-up, or clarification

Query: "{query}"

Respond with ONLY valid JSON: {{"intent":"...","reasoning":"...","required_tools":[]}}"""

        try:
            content = await self.client.chat_completion(
                system_prompt="Output ONLY valid JSON.",
                user_prompt=prompt,
                temperature=0,
                max_tokens=64,
                prompt_cache_key="supervisor-intent-classifier:v1",
            )
            
            if not content:
                raise ValueError("Empty response from LLM")
            
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
