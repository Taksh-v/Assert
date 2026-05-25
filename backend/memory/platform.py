"""Platform memory façade.

Provides a single import point `backend.memory.platform` that exposes the
common memory operations used across the codebase. Initially delegates to
the existing `backend.memory.manager` and `backend.agent.memory` implementations.

This file is a temporary seam to aid incremental consolidation into a
single `platform.memory` implementation.
"""
from typing import List, Dict, Any, Optional

from backend.memory.manager import MemoryManager as ObservationMemoryManager

class PlatformMemory:
    def __init__(self):
        # observation/reflector-based manager
        self._obs_mgr = ObservationMemoryManager()

    async def get_context_window(self, workspace_id: str, working_messages: List[Dict[str, str]], user_id: Optional[str] = None) -> str:
        return await self._obs_mgr.get_context_window(workspace_id=workspace_id, working_messages=working_messages, user_id=user_id)

    async def summarize_episode(self, user_id: str, workspace_id: str, new_interaction: str):
        # Legacy Agent memory has been deprecated in favor of Reflection memory
        pass

    async def store_observation(self, workspace_id: str, content: str, category: str = "general", user_id: Optional[str] = None, priority: float = 0.5) -> str:
        return await self._obs_mgr.store_observation(workspace_id=workspace_id, content=content, category=category, user_id=user_id, priority=priority)

    async def trigger_reflection(self, workspace_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        return await self._obs_mgr.trigger_reflection(workspace_id=workspace_id, user_id=user_id)

    async def get_relevant_memories(self, workspace_id: str, query: str, user_id: Optional[str] = None, limit: int = 3) -> List[Dict[str, Any]]:
        """Return a short list of memory items relevant to a query.

        This initially combines the top observation log items and the user's episodic/semantic
        memory (if available) into a prioritized list of small dicts used by retrieval.
        """
        # 1. Get recent observations (highest priority)
        obs = await self._obs_mgr.get_recent_observations(workspace_id=workspace_id, user_id=user_id, limit=limit)

        results = []
        for o in obs:
            results.append({"id": o["id"], "content": o["content"], "priority": o.get("priority", 0.5), "category": o.get("category")})

        # Trim to requested limit
        return results[:limit]


# Module-level singleton for convenience
_default = PlatformMemory()


def get_platform_memory() -> PlatformMemory:
    return _default
