"""
Observer Agent — Compresses raw conversation history into dated observations.

Inspired by Mastra's Observational Memory architecture. When the working memory
(raw messages) exceeds a configurable token threshold, the Observer compresses
them into concise, prioritized observation entries and stores them in the DB.
"""
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.core.config import get_settings
from backend.core.database import async_session
from backend.models.observation import Observation

settings = get_settings()
logger = logging.getLogger(__name__)

# Token counting — uses tiktoken if available, otherwise approximates
try:
    import tiktoken
    _encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_encoder.encode(text))
except Exception:
    # Offline or missing tiktoken: use word-based approximation
    logger.info("tiktoken unavailable or offline, using approximate token counting")

    def count_tokens(text: str) -> int:
        return len(text.split()) * 4 // 3  # ~1.33 tokens per word approximation


class ObserverAgent:
    """
    Watches the raw message stream and compresses it into observations
    when the token count exceeds the configured threshold.
    """

    # Default threshold in tokens before triggering compression
    DEFAULT_TOKEN_THRESHOLD = 8000

    def __init__(self, token_threshold: int = None):
        self.token_threshold = token_threshold or self.DEFAULT_TOKEN_THRESHOLD
        self._client = None
        self._client_init_failed = False

    @property
    def client(self):
        """Lazy-init Groq client."""
        if self._client is not None:
            return self._client
        if self._client_init_failed or not settings.groq_api_key:
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            return self._client
        except Exception as e:
            logger.warning(f"Observer: Groq client init failed: {e}")
            self._client_init_failed = True
            return None

    def should_compress(self, raw_messages: List[Dict[str, str]]) -> bool:
        """Check if the raw message stream exceeds the token threshold."""
        total_text = "\n".join(m.get("content", "") for m in raw_messages)
        token_count = count_tokens(total_text)
        logger.debug(f"Observer: Working memory at {token_count} tokens (threshold: {self.token_threshold})")
        return token_count > self.token_threshold

    async def compress(
        self,
        raw_messages: List[Dict[str, str]],
        workspace_id: str,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Compress raw messages into dated observation entries.

        Returns a list of observation dicts ready for DB insertion.
        Falls back to rule-based extraction if LLM is unavailable.
        """
        if not raw_messages:
            return []

        total_text = "\n".join(
            f"[{m.get('role', 'unknown')}]: {m.get('content', '')}"
            for m in raw_messages
        )

        observations = await self._compress_with_llm(total_text)
        if not observations:
            observations = self._compress_rule_based(raw_messages)

        # Persist to database
        saved = []
        async with async_session() as session:
            for obs in observations:
                record = Observation(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    content=obs["content"],
                    priority=obs.get("priority", 0.5),
                    category=obs.get("category", "general"),
                    token_count=count_tokens(obs["content"]),
                    is_active=True
                )
                session.add(record)
                saved.append(record)
            await session.commit()
            logger.info(f"Observer: Compressed {len(raw_messages)} messages into {len(saved)} observations")

        return [{"id": s.id, "content": s.content, "priority": s.priority} for s in saved]

    async def _compress_with_llm(self, text: str) -> List[Dict[str, Any]]:
        """Use LLM to extract key observations from conversation text."""
        if not self.client:
            return []

        prompt = f"""Analyze the following conversation and extract the most important observations.
Each observation should be a concise, dated fact that would be useful context for future conversations.

Categories: preference, decision, fact, tool_usage, error_pattern, relationship

Output ONLY valid JSON array:
[
  {{
    "content": "[{datetime.utcnow().strftime('%Y-%m-%d')}] Observation text here",
    "priority": 0.8,
    "category": "preference"
  }}
]

Rules:
- Extract 3-7 observations maximum
- Prioritize user preferences, key decisions, and recurring patterns
- Each observation must be self-contained (understandable without the original context)
- Priority: 0.9+ for critical decisions, 0.7-0.9 for preferences, 0.3-0.7 for general facts

Conversation:
{text[:6000]}

JSON Output:"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a memory compression agent. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=settings.groq_model,
                temperature=0,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            # Handle both direct array and wrapped object
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "observations" in data:
                return data["observations"]
            return []

        except Exception as e:
            logger.warning(f"Observer LLM compression failed: {e}")
            return []

    def _compress_rule_based(self, raw_messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Fallback: simple rule-based observation extraction."""
        observations = []
        today = datetime.utcnow().strftime('%Y-%m-%d')

        # Extract user messages as potential observations
        user_messages = [m for m in raw_messages if m.get("role") == "user"]

        if user_messages:
            # Group into a summary
            topics = set()
            for msg in user_messages:
                content = msg.get("content", "")
                # Extract key phrases (words > 4 chars, capitalized, or quoted)
                words = [w.strip(".,!?") for w in content.split() if len(w) > 4]
                topics.update(words[:5])

            if topics:
                observations.append({
                    "content": f"[{today}] User discussed topics: {', '.join(list(topics)[:10])}",
                    "priority": 0.4,
                    "category": "fact"
                })

        # Track conversation length as a meta-observation
        observations.append({
            "content": f"[{today}] Session contained {len(raw_messages)} messages. Compressed by Observer.",
            "priority": 0.2,
            "category": "general"
        })

        return observations
