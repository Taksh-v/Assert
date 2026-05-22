"""
Reflector Agent — Periodically reorganizes the observation log.

Merges related entries, resolves contradictions, and decays old/low-signal
observations. This keeps the observation log compact and cache-friendly,
ensuring the LLM context window remains stable and efficient.
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy import select, update
from backend.core.config import get_settings
from backend.core.database import async_session
from backend.models.observation import Observation

settings = get_settings()
logger = logging.getLogger(__name__)


class ReflectorAgent:
    """
    Periodically reorganizes the observation log for a workspace/user:
    1. Decay: Reduce priority of old observations
    2. Merge: Combine related/duplicate observations
    3. Prune: Archive observations below minimum priority threshold
    """

    # Observations older than this many days start decaying
    DECAY_THRESHOLD_DAYS = 14
    # Decay rate per reflection cycle (multiplied against current priority)
    DECAY_RATE = 0.85
    # Observations below this priority are archived (is_active=False)
    MIN_PRIORITY = 0.1
    # Maximum active observations to keep per workspace/user
    MAX_ACTIVE_OBSERVATIONS = 50

    def __init__(self):
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
            logger.warning(f"Reflector: Groq client init failed: {e}")
            self._client_init_failed = True
            return None

    async def reflect(
        self,
        workspace_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run a full reflection cycle on the observation log.
        Returns a summary of actions taken.
        """
        summary = {"decayed": 0, "merged": 0, "archived": 0}

        async with async_session() as session:
            # 1. Fetch all active observations
            stmt = select(Observation).where(
                Observation.workspace_id == workspace_id,
                Observation.is_active == True
            )
            if user_id:
                stmt = stmt.where(Observation.user_id == user_id)
            stmt = stmt.order_by(Observation.priority.desc(), Observation.created_at.desc())

            result = await session.execute(stmt)
            observations = result.scalars().all()

            if not observations:
                logger.info(f"Reflector: No active observations for workspace {workspace_id}")
                return summary

            logger.info(f"Reflector: Processing {len(observations)} active observations")

            # 2. Decay old observations
            cutoff = datetime.utcnow() - timedelta(days=self.DECAY_THRESHOLD_DAYS)
            for obs in observations:
                if obs.created_at < cutoff:
                    old_priority = obs.priority
                    obs.priority = round(obs.priority * self.DECAY_RATE, 3)
                    obs.updated_at = datetime.utcnow()
                    summary["decayed"] += 1

            # 3. Archive observations below minimum priority
            for obs in observations:
                if obs.priority < self.MIN_PRIORITY:
                    obs.is_active = False
                    obs.updated_at = datetime.utcnow()
                    summary["archived"] += 1

            # 4. Attempt LLM-powered merge of related observations
            active_obs = [o for o in observations if o.is_active]
            if len(active_obs) > 10 and self.client:
                merge_result = await self._merge_related(active_obs, session)
                summary["merged"] = merge_result

            # 5. Enforce maximum observation count
            still_active = [o for o in observations if o.is_active]
            if len(still_active) > self.MAX_ACTIVE_OBSERVATIONS:
                # Archive the lowest-priority excess
                sorted_by_priority = sorted(still_active, key=lambda o: o.priority)
                excess = len(still_active) - self.MAX_ACTIVE_OBSERVATIONS
                for obs in sorted_by_priority[:excess]:
                    obs.is_active = False
                    obs.updated_at = datetime.utcnow()
                    summary["archived"] += 1

            await session.commit()

        logger.info(f"Reflector: Cycle complete — {summary}")
        return summary

    async def _merge_related(self, observations: List[Observation], session) -> int:
        """Use LLM to identify and merge related observations."""
        if len(observations) < 5:
            return 0

        # Prepare observation summaries for the LLM
        obs_text = "\n".join(
            f"[ID:{i}] (priority={obs.priority}, cat={obs.category}) {obs.content}"
            for i, obs in enumerate(observations[:30])  # Cap at 30 to avoid context overflow
        )

        prompt = f"""Analyze these observations and identify groups that should be merged.
Two observations should be merged if they:
- Say the same thing in different words
- Are about the same topic and can be combined into one richer entry
- Contradict each other (keep the more recent/higher-priority one)

Output ONLY valid JSON:
{{
  "merge_groups": [
    {{
      "ids": [0, 3],
      "merged_content": "The combined observation text",
      "category": "preference",
      "priority": 0.8
    }}
  ]
}}

If no merges are needed, return: {{"merge_groups": []}}

Observations:
{obs_text}

JSON Output:"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a memory organization agent. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=settings.groq_model,
                temperature=0,
                response_format={"type": "json_object"}
            )

            data = json.loads(response.choices[0].message.content)
            merge_groups = data.get("merge_groups", [])
            merge_count = 0

            for group in merge_groups:
                ids = group.get("ids", [])
                if len(ids) < 2:
                    continue

                # Create the merged observation
                merged = Observation(
                    workspace_id=observations[0].workspace_id,
                    user_id=observations[0].user_id,
                    content=group["merged_content"],
                    priority=group.get("priority", 0.7),
                    category=group.get("category", "general"),
                    is_active=True
                )
                session.add(merged)

                # Mark source observations as superseded
                for idx in ids:
                    if 0 <= idx < len(observations):
                        observations[idx].is_active = False
                        observations[idx].superseded_by = merged.id
                        observations[idx].updated_at = datetime.utcnow()

                merge_count += 1

            return merge_count

        except Exception as e:
            logger.warning(f"Reflector LLM merge failed: {e}")
            return 0
