import asyncio
import os
import sys
from unittest.mock import MagicMock

# Ensure backend directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Reuse test environment mocks similar to test_ingestion_dlq
class MockCryptContext:
    def __init__(self, *args, **kwargs):
        pass
    def verify(self, plain, hashed):
        return True
    def hash(self, password):
        return "hashed"

mock_passlib = MagicMock()
mock_passlib.context = MagicMock()
mock_passlib.context.CryptContext = MockCryptContext
sys.modules["passlib"] = mock_passlib
sys.modules["passlib.context"] = mock_passlib.context

sys.modules["groq"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()

class MockRawDocument:
    def __init__(self, title, content, source_id, source_url):
        self.title = title
        self.raw_content = content
        self.source_id = source_id
        self.source_url = source_url
        self.source_type = "slack"
        self.content_format = "text"
        self.tier = 2
        self.content_hash = f"hash_{source_id}"

class CorruptedMockRawDocument:
    def __init__(self, title, source_id, source_url):
        self.title = title
        self.source_id = source_id
        self.source_url = source_url
        self.source_type = "slack"
        self.content_format = "text"
        self.tier = 2
        self.content_hash = f"hash_{source_id}"
    @property
    def raw_content(self):
        raise ValueError("Simulated corruption in document stream")

class MockSlackConnector:
    async def connect(self, config):
        return "mock_connection"
    async def fetch_documents(self, connection, since=None, selected_ids=None):
        yield MockRawDocument("Doc 1", "Content of doc 1", "id-1", "slack://msg1")
        yield CorruptedMockRawDocument("Corrupted Doc", "id-2", "slack://msg2")
        yield MockRawDocument("Doc 3", "Content of doc 3", "id-3", "slack://msg3")

from backend.connectors.registry import connector_registry
connector_registry.register("slack", MockSlackConnector)

from backend.core.database import init_db, close_db, async_session
from backend.models.connector import Connector, ConnectorType, ConnectorStatus
from backend.models.failed_ingestion import FailedIngestion
from backend.models.document import Document
from backend.ingestion.pipeline import IngestionPipeline
from backend.workers.sync_runner import ConnectorSyncRunner
from backend.models.sync_run import SyncRun, SyncRunStatus
from sqlalchemy import select


async def test_pilot_parity_legacy_vs_new(offline_ingestion_mocks):
    await init_db()

    # Legacy run
    workspace_legacy = "pilot-ws-legacy"
    connector_legacy_id = "pilot-connector-legacy"
    async with async_session() as session:
        # Clean
        from sqlalchemy import delete
        await session.execute(delete(Document).where(Document.workspace_id == workspace_legacy))
        await session.execute(delete(FailedIngestion).where(FailedIngestion.workspace_id == workspace_legacy))
        # Remove any existing connector with same id
        from backend.models.connector import Connector as _ConnectorModel
        await session.execute(delete(_ConnectorModel).where(_ConnectorModel.id == connector_legacy_id))
        # Insert connector
        conn = Connector(id=connector_legacy_id, workspace_id=workspace_legacy, type=ConnectorType.SLACK, config={}, status=ConnectorStatus.ACTIVE)
        session.add(conn)
        await session.commit()

    pipeline = IngestionPipeline()
    # Mock heavy external stores to keep test deterministic and offline
    import backend.ingestion.pipeline as _pipeline_mod
    # Keep external stores unmocked to reproduce legacy behavior deterministically in this environment
    legacy_stats = await pipeline.run(connector_legacy_id)

    async with async_session() as session:
        stmt = select(Document).where(Document.workspace_id == workspace_legacy, Document.is_active == True)
        res = await session.execute(stmt)
        documents = res.scalars().all()
        titles_legacy = {d.title for d in documents}
        stmt = select(FailedIngestion).where(FailedIngestion.workspace_id == workspace_legacy)
        res = await session.execute(stmt)
        failed_legacy = res.scalars().all()

    # Clean DB for new run
    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(Document).where(Document.workspace_id == workspace_legacy))
        await session.execute(delete(FailedIngestion).where(FailedIngestion.workspace_id == workspace_legacy))
        await session.commit()

    # New runner run
    workspace_new = "pilot-ws-new"
    connector_new_id = "pilot-connector-new"
    async with async_session() as session:
        from sqlalchemy import delete
        from backend.models.connector import Connector as _ConnectorModel
        # Clean any previous documents/failed ingestions for this workspace
        await session.execute(delete(Document).where(Document.workspace_id == workspace_new))
        await session.execute(delete(FailedIngestion).where(FailedIngestion.workspace_id == workspace_new))
        await session.execute(delete(_ConnectorModel).where(_ConnectorModel.id == connector_new_id))
        conn = Connector(id=connector_new_id, workspace_id=workspace_new, type=ConnectorType.SLACK, config={}, status=ConnectorStatus.ACTIVE)
        session.add(conn)
        await session.commit()

    # Create SyncRun for connector_new
    async with async_session() as session:
        sync_run = SyncRun(connector_id=connector_new_id, workspace_id=workspace_new, triggered_by="pilot", status=SyncRunStatus.QUEUED)
        session.add(sync_run)
        await session.flush()
        run_id = sync_run.id
        await session.commit()

    # Use ConnectorSyncRunner path for the new run (pilot) but inject a dummy Qdrant client
    # to avoid hitting local qdrant files in CI/dev environments.
    import backend.core.vector_store as _vs
    class _DummyQdrant:
        def __init__(self):
            pass
        def upsert(self, *args, **kwargs):
            return None
        def get_collections(self):
            class C: collections = []
            return C()
        def create_collection(self, *args, **kwargs):
            return None
        def create_payload_index(self, *args, **kwargs):
            return None
        def query_points(self, *args, **kwargs):
            class R: points = []
            return R()

    _vs._GLOBAL_QDRANT_CLIENT = _DummyQdrant()

    runner = ConnectorSyncRunner()
    new_stats = await runner.run(run_id)

    async with async_session() as session:
        stmt = select(Document).where(Document.workspace_id == workspace_new, Document.is_active == True)
        res = await session.execute(stmt)
        documents_new = res.scalars().all()
        titles_new = {d.title for d in documents_new}
        stmt = select(FailedIngestion).where(FailedIngestion.workspace_id == workspace_new)
        res = await session.execute(stmt)
        failed_new = res.scalars().all()

    # Assertions: document titles and failed counts should match expected
    expected_titles = {"Doc 1", "Doc 3"}
    assert titles_legacy == expected_titles
    assert titles_new == expected_titles
    assert len(failed_legacy) == 1
    assert len(failed_new) == 1
    assert failed_legacy[0].source_url == "slack://msg2"
    assert failed_new[0].source_url == "slack://msg2"

    await close_db()


if __name__ == "__main__":
    asyncio.run(test_pilot_parity_legacy_vs_new())
