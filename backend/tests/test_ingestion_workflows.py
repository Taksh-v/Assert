import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_workflows.db"

import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY

# Mock passlib and other heavy dependencies
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

# Source-level mocks for external connections to run 100% offline and prevent hangs
import backend.core.vector_store
backend.core.vector_store.get_qdrant_client = MagicMock()
backend.core.vector_store._GLOBAL_QDRANT_CLIENT = MagicMock()
backend.core.vector_store.VectorStore.upsert_batch = MagicMock()
backend.core.vector_store.VectorStore.create_collection = MagicMock()

import backend.graph.graph_store
backend.graph.graph_store.GraphStore.add_document_node = MagicMock()
backend.graph.graph_store.GraphStore.add_entities_and_relationships = MagicMock()
backend.graph.graph_store.GraphStore.add_event_node = MagicMock()

import backend.graph.entity_resolver
backend.graph.entity_resolver.EntityResolver.resolve_and_link = AsyncMock(return_value=[])


# Import all models to ensure they are registered on Base metadata
import backend.models.connector
import backend.models.connector_sync_state
import backend.models.failed_ingestion
import backend.models.document
import backend.models.chunk
import backend.models.knowledge_event
import backend.models.knowledge_object
import backend.models.background_task
import backend.models.reasoning_execution

from backend.core.database import init_db, close_db, async_session
from backend.models.connector import Connector, ConnectorType, ConnectorStatus
from backend.models.failed_ingestion import FailedIngestion
from backend.models.document import Document
from sqlalchemy import select

from backend.ingestion.activities import (
    fetch_documents_activity,
    scrub_document_activity,
    index_document_activity,
    build_graph_activity,
    record_failed_ingestion_activity,
)
from backend.ingestion.workflows import IngestionWorkflow
from backend.connectors.registry import connector_registry


class MockDoc:
    def __init__(self, title, content, source_id, source_url):
        self.title = title
        self.raw_content = content
        self.source_id = source_id
        self.source_url = source_url
        self.source_type = "slack"
        self.content_format = "text"
        self.tier = 2
        self.content_hash = f"hash_{source_id}"


class MockWorkflowSlackConnector:
    async def connect(self, config):
        return "mock_connection"

    async def fetch_documents(self, connection, since=None, selected_ids=None):
        yield MockDoc("Doc 1", "Content of doc 1", "id-1", "slack://msg1")
        yield MockDoc("Doc 2", None, "id-2", "slack://msg2") # None content simulates failure during parsing/scrubbing


@pytest.fixture(autouse=True)
def setup_mocks(offline_ingestion_mocks):
    original = None
    try:
        original = connector_registry.get_connector("slack")
    except Exception:
        pass

    connector_registry.register("slack", MockWorkflowSlackConnector)
    yield

    if original:
        connector_registry.register("slack", original)
    else:
        if "slack" in connector_registry._registry:
            del connector_registry._registry["slack"]


@pytest.mark.asyncio
async def test_workflows_sync_runs_activities_in_order():
    mock_docs = [
        {
            "source_id": "doc1",
            "title": "Document 1",
            "raw_content": "Clean content",
            "is_base64": False,
            "source_url": "http://example.com/doc1",
            "metadata": {},
            "permissions": [],
            "content_format": "text",
            "tier": 2,
            "content_hash": "hash1",
            "workspace_id": "test_ws",
            "connector_id": "test_conn",
            "source_type": "slack",
        }
    ]

    mock_scrubbed = {
        "title": "Document 1",
        "content": "Clean content",
        "elements": [{"type": "text", "content": "Clean content", "metadata": {}}],
        "metadata": {"document_type": "general"},
        "raw_doc": mock_docs[0]
    }

    mock_index_res = {
        "document_id": "doc_uuid_123",
        "title": "Document 1",
        "source_url": "http://example.com/doc1",
        "entities": [],
        "events": [],
        "should_skip": False
    }

    async def side_effect(activity, *args, **kwargs):
        if activity == fetch_documents_activity:
            return mock_docs
        elif activity == scrub_document_activity:
            return mock_scrubbed
        elif activity == index_document_activity:
            return mock_index_res
        elif activity == build_graph_activity:
            return None
        return None

    with patch("temporalio.workflow.execute_activity", new=AsyncMock(side_effect=side_effect)) as mock_execute:
        wf = IngestionWorkflow()
        result = await wf.run_sync("test_conn")

        assert "Sync successful for test_conn" in result
        assert "processed 1/1" in result
        
        # Verify execute_activity calls
        mock_execute.assert_any_call(
            fetch_documents_activity,
            "test_conn",
            start_to_close_timeout=ANY
        )
        mock_execute.assert_any_call(
            scrub_document_activity,
            mock_docs[0],
            start_to_close_timeout=ANY
        )
        mock_execute.assert_any_call(
            index_document_activity,
            mock_scrubbed,
            "test_ws",
            "test_conn",
            start_to_close_timeout=ANY
        )
        mock_execute.assert_any_call(
            build_graph_activity,
            mock_index_res,
            "test_ws",
            start_to_close_timeout=ANY
        )


@pytest.mark.asyncio
async def test_workflows_records_failures_to_dlq():
    mock_docs = [
        {
            "source_id": "doc2",
            "title": "Document 2",
            "raw_content": None,
            "is_base64": False,
            "source_url": "http://example.com/doc2",
            "metadata": {},
            "permissions": [],
            "content_format": "text",
            "tier": 2,
            "content_hash": "hash2",
            "workspace_id": "test_ws",
            "connector_id": "test_conn",
            "source_type": "slack",
        }
    ]

    async def side_effect(activity, *args, **kwargs):
        if activity == fetch_documents_activity:
            return mock_docs
        elif activity == scrub_document_activity:
            raise ValueError("PII scrub failed due to missing content")
        return None

    with patch("temporalio.workflow.execute_activity", new=AsyncMock(side_effect=side_effect)) as mock_execute:
        wf = IngestionWorkflow()
        result = await wf.run_sync("test_conn")

        assert "Sync successful for test_conn" in result
        assert "processed 0/1" in result

        mock_execute.assert_any_call(
            record_failed_ingestion_activity,
            "test_ws",
            "slack",
            "http://example.com/doc2",
            "PII scrub failed due to missing content",
            start_to_close_timeout=ANY
        )


@pytest.mark.asyncio
async def test_activities_direct_run():
    await init_db()

    workspace_id = "test-workflow-ws"
    connector_id = "test-workflow-conn"

    # Seed connector and clean old data
    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(Document).where(Document.workspace_id == workspace_id))
        await session.execute(delete(FailedIngestion).where(FailedIngestion.workspace_id == workspace_id))
        await session.execute(delete(Connector).where(Connector.id == connector_id))
        await session.commit()

        connector = Connector(
            id=connector_id,
            workspace_id=workspace_id,
            type=ConnectorType.SLACK,
            config={},
            status=ConnectorStatus.ACTIVE
        )
        session.add(connector)
        await session.commit()

    # 1. Test fetch documents activity
    docs = await fetch_documents_activity(connector_id)
    assert len(docs) == 2
    assert docs[0]["title"] == "Doc 1"
    assert docs[1]["title"] == "Doc 2"

    # 2. Test scrub document activity (success case)
    scrubbed = await scrub_document_activity(docs[0])
    assert scrubbed["title"] == "Doc 1"
    assert scrubbed["content"] == "Content of doc 1"

    # 3. Test index document activity (success case)
    index_res = await index_document_activity(scrubbed, workspace_id, connector_id)
    assert index_res["document_id"] is not None
    assert index_res["should_skip"] is False

    # 4. Test build graph activity
    await build_graph_activity(index_res, workspace_id)

    # 5. Test record failed ingestion activity
    await record_failed_ingestion_activity(workspace_id, "slack", "slack://msg2", "Simulated failure")

    # Verify database state
    async with async_session() as session:
        stmt = select(Document).where(Document.workspace_id == workspace_id)
        res = await session.execute(stmt)
        documents = res.scalars().all()
        assert len(documents) == 1
        assert documents[0].title == "Doc 1"

        stmt = select(FailedIngestion).where(FailedIngestion.workspace_id == workspace_id)
        res = await session.execute(stmt)
        failed = res.scalars().all()
        assert len(failed) == 1
        assert failed[0].source_url == "slack://msg2"
        assert failed[0].error_message == "Simulated failure"

    await close_db()
