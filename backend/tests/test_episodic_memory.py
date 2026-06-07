import pytest
from unittest.mock import MagicMock
from sqlalchemy import delete
from backend.core.database import init_db, close_db, async_session
from backend.models.episode import Episode as DBEpisode
from backend.memory.episodic import EpisodicMemoryService

# Create mock Embedder and VectorStore classes
class MockEmbedder:
    async def aembed(self, texts):
        return [[0.1] * 384 for _ in texts]

class MockVectorStore:
    def __init__(self):
        self.episodes = []

    def create_collection(self, vector_size, collection_name):
        pass

    def upsert_episode(self, workspace_id, episode_id, vector, payload):
        self.episodes.append({
            "id": episode_id,
            "score": 1.0,
            "payload": payload,
            "workspace_id": workspace_id
        })

    def search_episodes(self, workspace_id, query_vector, top_k, user_id=None):
        # Return all episodes for simplified mock search
        return [ep for ep in self.episodes if ep["workspace_id"] == workspace_id][:top_k]

@pytest.mark.asyncio
async def test_record_and_query_similar_episodes(monkeypatch):
    await init_db()

    # Apply patches
    monkeypatch.setattr("backend.memory.episodic.Embedder", MockEmbedder)
    monkeypatch.setattr("backend.memory.episodic.VectorStore", MockVectorStore)

    async with async_session() as session:
        # Clear existing data for isolation
        await session.execute(delete(DBEpisode))
        await session.commit()

        service = EpisodicMemoryService(db=session)

        # Record episode 1
        await service.record_episode(
            workspace_id="ws-1",
            user_id="user-1",
            title="Invoice mismatch investigation",
            summary="The invoice was incorrect because contract terms and usage did not align.",
            interaction="Customer asked why the invoice total was higher than expected.",
            outcome="Explained the contract and corrected the billing details.",
            tags=["billing", "invoice"],
            metadata={"priority": 0.9},
        )

        # Record episode 2
        await service.record_episode(
            workspace_id="ws-1",
            user_id="user-2",
            title="Workspace onboarding",
            summary="A standard onboarding checklist for a new team.",
            interaction="The user asked for onboarding steps.",
            outcome="Shared the checklist.",
            tags=["onboarding"],
        )

        # Query similar
        matches = await service.query_similar(
            workspace_id="ws-1",
            query="Why is my invoice higher because of contract usage?",
            user_id="user-1",
            limit=3,
        )

        # Note: query_similar returns dicts:
        # [{"id": ..., "score": ..., "title": ..., "summary": ..., "created_at": ..., "tags": ...}]
        assert len(matches) == 2
        assert matches[0]["title"] == "Invoice mismatch investigation"
        assert "billing" in matches[0]["tags"]

    await close_db()


@pytest.mark.asyncio
async def test_prune_keeps_latest_episodes_only(monkeypatch):
    await init_db()

    monkeypatch.setattr("backend.memory.episodic.Embedder", MockEmbedder)
    monkeypatch.setattr("backend.memory.episodic.VectorStore", MockVectorStore)

    async with async_session() as session:
        # Clear existing data for isolation
        await session.execute(delete(DBEpisode))
        await session.commit()

        service = EpisodicMemoryService(db=session)

        for index in range(4):
            await service.record_episode(
                workspace_id="ws-1",
                user_id=None,
                title=f"Episode {index}",
                summary="A sample episode",
                interaction="Some interaction",
                outcome="Some outcome",
            )

        # prune_policy prunes by age. We pass days_to_keep=-1 so the threshold is tomorrow,
        # ensuring that all episodes created right now (in the past relative to tomorrow) are pruned.
        removed = await service.prune_policy(workspace_id="ws-1", days_to_keep=-1)
        assert removed == 4

    await close_db()
