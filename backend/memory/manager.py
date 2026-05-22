"""
Agentic Memory Manager — Mastra-inspired Observational Memory Architecture.

Manages a two-block context window:
  1. Observation Log: Compressed, dated facts from past sessions (managed by Observer/Reflector)
  2. Working Memory: Recent raw messages from the current session

The Observer compresses working memory when it exceeds a token threshold.
The Reflector periodically decays, merges, and prunes old observations.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy import select
from backend.core.database import async_session
from backend.models.observation import Observation
from backend.memory.observer import ObserverAgent, count_tokens
from backend.memory.reflector import ReflectorAgent

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Blueprint Layer 16: Agentic Memory Manager.

    Assembles a two-block context window for LLM prompts:
    - Block 1: Compressed observation log (long-term memory)
    - Block 2: Raw recent messages (short-term working memory)

    Automatically triggers the Observer when working memory grows too large,
    and the Reflector when the observation log needs maintenance.
    """

    # Maximum tokens for the full memory context (observation + working)
    MAX_CONTEXT_TOKENS = 12000
    # Budget split: 40% observation log, 60% working memory
    OBSERVATION_BUDGET_RATIO = 0.4

    def __init__(self):
        self.observer = ObserverAgent()
        self.reflector = ReflectorAgent()

    async def get_context_window(
        self,
        workspace_id: str,
        working_messages: List[Dict[str, str]],
        user_id: Optional[str] = None,
    ) -> str:
        """
        Assemble the full two-block context window.

        If working memory exceeds the Observer's threshold, compress it first.
        Returns a formatted string ready for LLM prompt injection.
        """
        # 1. Check if working memory needs compression
        if self.observer.should_compress(working_messages):
            logger.info("MemoryManager: Working memory exceeded threshold, triggering Observer")
            await self.observer.compress(working_messages, workspace_id, user_id)
            # After compression, keep only the last few messages as working memory
            working_messages = working_messages[-5:]

        # 2. Fetch observation log from DB
        observation_budget = int(self.MAX_CONTEXT_TOKENS * self.OBSERVATION_BUDGET_RATIO)
        observations = await self._get_observation_log(workspace_id, user_id, observation_budget)

        # 3. Format working memory
        working_budget = self.MAX_CONTEXT_TOKENS - count_tokens(observations)
        working_text = self._format_working_memory(working_messages, working_budget)

        # 4. Assemble the two-block context
        blocks = []
        if observations:
            blocks.append(f"## AGENT MEMORY (Compressed Observations)\n{observations}")
        if working_text:
            blocks.append(f"## RECENT CONVERSATION\n{working_text}")

        return "\n\n---\n\n".join(blocks)

    async def store_observation(
        self,
        workspace_id: str,
        content: str,
        category: str = "general",
        user_id: Optional[str] = None,
        priority: float = 0.5
    ) -> str:
        """Store a new observation directly (e.g., from reasoning outputs)."""
        async with async_session() as session:
            obs = Observation(
                workspace_id=workspace_id,
                user_id=user_id,
                content=f"[{datetime.utcnow().strftime('%Y-%m-%d')}] {content}",
                category=category,
                priority=priority,
                token_count=count_tokens(content),
                is_active=True
            )
            session.add(obs)
            await session.commit()
            logger.info(f"Memory stored: [{category}] {content[:50]}...")
            return obs.id

    async def trigger_reflection(
        self,
        workspace_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Trigger a Reflector cycle to maintain the observation log."""
        return await self.reflector.reflect(workspace_id, user_id)

    async def get_observation_count(
        self,
        workspace_id: str,
        user_id: Optional[str] = None
    ) -> int:
        """Get the count of active observations."""
        async with async_session() as session:
            stmt = select(Observation).where(
                Observation.workspace_id == workspace_id,
                Observation.is_active == True
            )
            if user_id:
                stmt = stmt.where(Observation.user_id == user_id)
            result = await session.execute(stmt)
            return len(result.scalars().all())

    # ── Private helpers ──────────────────────────────────────

    async def _get_observation_log(
        self,
        workspace_id: str,
        user_id: Optional[str],
        token_budget: int
    ) -> str:
        """Fetch active observations within the token budget, highest priority first."""
        async with async_session() as session:
            stmt = select(Observation).where(
                Observation.workspace_id == workspace_id,
                Observation.is_active == True
            )
            if user_id:
                stmt = stmt.where(Observation.user_id == user_id)
            stmt = stmt.order_by(Observation.priority.desc(), Observation.created_at.desc())

            result = await session.execute(stmt)
            observations = result.scalars().all()

        # Assemble within token budget
        lines = []
        running_tokens = 0
        for obs in observations:
            line = f"- {obs.content}"
            line_tokens = count_tokens(line)
            if running_tokens + line_tokens > token_budget:
                break
            lines.append(line)
            running_tokens += line_tokens

        return "\n".join(lines)

    def _format_working_memory(
        self,
        messages: List[Dict[str, str]],
        token_budget: int
    ) -> str:
        """Format recent messages within the token budget."""
        lines = []
        running_tokens = 0

        # Process from most recent to oldest (keep the most recent)
        for msg in reversed(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            line = f"[{role}]: {content}"
            line_tokens = count_tokens(line)

            if running_tokens + line_tokens > token_budget:
                break
            lines.insert(0, line)  # Maintain chronological order
            running_tokens += line_tokens

        return "\n".join(lines)
