import logging
import json
import re
from typing import Dict, Any, Optional
from backend.core.llm_client import LLMClient
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class CognitiveProfiler:
    """
    Evaluates the emotional and expertise profile of a user query
    to tailor the response tone and depth.
    """
    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    async def profile_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze the query to detect tone, complexity, and expertise level.
        """
        system_prompt = (
            "You are a cognitive psychology profiler. Analyze the user's query and output ONLY valid JSON "
            "with keys: 'tone' (e.g., neutral, frustrated, confused, curious), 'complexity' (high, medium, low), "
            "and 'expertise' (beginner, intermediate, advanced) based on the vocabulary and style of query."
        )
        user_prompt = f"Query: \"{query}\"\nProvide the profile JSON."

        try:
            response = await self.llm.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=64,
                prompt_cache_key="cognitive-profiler:v1"
            )
            
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                data = json.loads(cleaned)
                
            return {
                "tone": str(data.get("tone", "neutral")),
                "complexity": str(data.get("complexity", "medium")),
                "expertise": str(data.get("expertise", "intermediate"))
            }
        except Exception as e:
            logger.warning(f"Cognitive profiling failed (falling back to default): {e}")
            return {
                "tone": "neutral",
                "complexity": "medium",
                "expertise": "intermediate"
            }


class ValueAlignmentFilter:
    """
    Enforces ethical and security boundaries on final outputs before delivery.
    Blocks key leakage and enforces objective trade-off presentations.
    """
    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    def inspect_security(self, content: str) -> str:
        """
        Scan content for high-risk security patterns (API keys, credentials) and redact them.
        """
        # Redact generic password/secret assignments
        redacted = re.sub(
            r"(?i)(password|passwd|secret|apikey|api_key|client_secret|db_password)\s*[:=]\s*['\"][^'\"]{3,}['\"]",
            r"\1: '[REDACTED]'",
            content
        )
        
        # Redact standard JWT/Auth headers or keys
        redacted = re.sub(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{15,}", "Bearer [REDACTED]", redacted)
        
        return redacted

    async def filter_values(self, question: str, answer: str) -> str:
        """
        Sanitize response and ensure ethical value alignment.
        """
        # 1. First redact credential patterns
        cleaned_answer = self.inspect_security(answer)
        
        # 2. Check value alignment (ethical framing of trade-offs) using LLM
        system_prompt = (
            "You are an ethical value alignment bot. Your task is to verify if the generated answer is neutral, "
            "objective, and does not leak credentials or promote harmful behavior. If the answer is already aligned, "
            "output it EXACTLY as is. If it has subjective bias on trade-offs or leaks keys, rewrite it to be neutral "
            "and clean."
        )
        user_prompt = f"[QUESTION]: {question}\n\n[ANSWER]:\n{cleaned_answer}\n\nProvide aligned answer."

        try:
            aligned = await self.llm.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=1024,
                prompt_cache_key="value-filter:v1"
            )
            if aligned and len(aligned.strip()) > 10:
                return aligned.strip()
            return cleaned_answer
        except Exception as e:
            logger.warning(f"Value filter LLM check failed (falling back to simple redaction): {e}")
            return cleaned_answer
