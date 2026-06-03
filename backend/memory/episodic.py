"""Episodic memory service MVP.

Implements record_episode(episode), query_similar(embedding, filters), and prune_policy.
Uses Qdrant (via VectorStore) for similarity search and metadata in Postgres.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.models.episode import Episode as DBEpisode
from backend.core.vector_store import VectorStore
from backend.ingestion.embedder import Embedder
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class EpisodicMemoryService:
    """Persist and retrieve episodic interaction memory using Vector + SQL."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.vector_store = VectorStore()
        self.embedder = Embedder()

    async def record_episode(
        self,
        workspace_id: str,
        title: str,
        summary: str,
        interaction: str,
        outcome: str,
        user_id: Optional[str] = None,
        tags: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> DBEpisode:
        """Record a new interaction episode."""
        # 1. Persist to Postgres
        episode = DBEpisode(
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            summary=summary,
            interaction=interaction,
            outcome=outcome,
            tags=tags or [],
            extra_metadata=metadata or {},
        )
        self.db.add(episode)
        await self.db.flush() # Get the generated ID
        
        # 2. Generate embedding and store in Qdrant
        # We embed the summary and title for similarity search
        text_to_embed = f"{title}\n\n{summary}"
        embedding = (await self.embedder.aembed([text_to_embed]))[0]
        
        # Ensure collection exists (lazy creation)
        # Assuming 384 for default local model, 1536 for OpenAI
        vector_size = 1536 if settings.embedding_provider == "openai" else 384
        await run_in_thread(
            self.vector_store.create_collection, 
            vector_size, 
            settings.qdrant_episodes_collection_name
        )

        payload = {
            "title": title,
            "summary": summary,
            "user_id": user_id,
            "tags": tags or [],
            "created_at": episode.created_at.isoformat() if episode.created_at else datetime.now(timezone.utc).isoformat()
        }
        
        await run_in_thread(
            self.vector_store.upsert_episode,
            workspace_id=workspace_id,
            episode_id=episode.id,
            vector=embedding,
            payload=payload
        )
        
        await self.db.commit()
        await self.db.refresh(episode)
        logger.info(f"Recorded episode: {episode.id} ('{title}')")
        return episode

    async def query_similar(
        self,
        workspace_id: str,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Query for similar episodes using vector similarity."""
        # 1. Generate query embedding
        embedding = (await self.embedder.aembed([query]))[0]
        
        # 2. Search Qdrant
        results = await run_in_thread(
            self.vector_store.search_episodes,
            workspace_id=workspace_id,
            query_vector=embedding,
            top_k=limit,
            user_id=user_id
        )
        
        # 3. Enhance with Postgres data if needed, or just return payloads
        # For MVP, payload is sufficient
        return [
            {
                "id": res["id"],
                "score": res["score"],
                "title": res["payload"].get("title"),
                "summary": res["payload"].get("summary"),
                "created_at": res["payload"].get("created_at"),
                "tags": res["payload"].get("tags", [])
            }
            for res in results
        ]

    async def prune_policy(self, workspace_id: str, days_to_keep: int = 30):
        """Prune episodes older than a certain threshold."""
        threshold = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        # 1. Delete from Postgres
        stmt = delete(DBEpisode).where(
            DBEpisode.workspace_id == workspace_id,
            DBEpisode.created_at < threshold
        )
        result = await self.db.execute(stmt)
        count = result.rowcount
        
        # 2. Qdrant pruning (best-effort)
        # For simplicity, we skip precise Qdrant deletion in MVP unless IDs are tracked
        # Qdrant supports TTL in some versions or filtered deletion
        
        await self.db.commit()
        logger.info(f"Pruned {count} episodes for workspace {workspace_id}")
        return count

async def run_in_thread(func, *args, **kwargs):
    import asyncio
    return await asyncio.to_thread(func, *args, **kwargs)
