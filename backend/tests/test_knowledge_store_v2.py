import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from backend.ingestion.pipeline_v2 import KnowledgeStore
from backend.ingestion.document_run import IngestionPackage, IngestionState
from backend.ingestion.document_store import VersionPlan

@pytest.fixture
def mock_vector_store():
    return MagicMock()

@pytest.fixture
def mock_graph_store():
    return MagicMock()

@pytest.fixture
def mock_entity_resolver():
    resolver = MagicMock()
    resolver.resolve_and_link = AsyncMock(return_value=[{"name": "Entity1", "type": "Person"}])
    return resolver

@pytest.fixture
def mock_raw_doc():
    doc = MagicMock()
    doc.source_url = "http://example.com"
    doc.title = "Test Doc"
    doc.source_type = "web"
    doc.content_hash = "hash123"
    doc.tier = 2
    return doc

@pytest.fixture
def ingestion_package(mock_raw_doc):
    package = IngestionPackage(
        raw_doc=mock_raw_doc,
        workspace_id="ws_123",
        connector_id="conn_456"
    )
    package.title = "Test Doc"
    package.content = "Some content"
    package.chunks = ["chunk1", "chunk2"]
    package.embeddings = [{"vector": [0.1, 0.2]}]
    package.metadata = {
        "document_type": "article",
        "keywords": ["test"],
        "entities": [{"name": "Entity1"}],
        "events": [{"type": "milestone", "title": "Found something"}]
    }
    return package

@pytest.mark.asyncio
async def test_knowledge_store_persist_new_doc(
    mock_vector_store, 
    mock_graph_store, 
    mock_entity_resolver, 
    ingestion_package
):
    store = KnowledgeStore(
        vector_store=mock_vector_store,
        graph_store=mock_graph_store,
        entity_resolver=mock_entity_resolver
    )

    # Mock DB session - use MagicMock for sync methods, AsyncMock for async ones
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.merge = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    with patch("backend.ingestion.pipeline_v2.async_session") as mock_async_session:
        mock_async_session.return_value.__aenter__.return_value = mock_session
        
        # Mocking select(Document) result for prepare_version
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result
        
        await store.persist(ingestion_package)

    # Assertions
    assert ingestion_package.state == IngestionState.PERSISTED
    assert ingestion_package.doc_record is not None
    assert ingestion_package.doc_record.title == "Test Doc"
    
    # Verify SQL calls
    # session.add is called for Document, 2 Chunks, 1 Event
    assert mock_session.add.call_count == 4 
    # Only 1 commit (in persist) because prepare_version returned early
    assert mock_session.commit.call_count == 1 
    
    # Verify Vector Store call
    mock_vector_store.upsert_batch.assert_called_once()
    
    # Verify Graph Store calls
    mock_graph_store.add_document_node.assert_called_once()
    mock_graph_store.add_entities_and_relationships.assert_called_once()
    mock_graph_store.add_event_node.assert_called_once()
    
    # Verify Entity Resolver call
    mock_entity_resolver.resolve_and_link.assert_called_once()

@pytest.mark.asyncio
async def test_knowledge_store_deduplication(
    mock_vector_store, 
    ingestion_package
):
    store = KnowledgeStore(vector_store=mock_vector_store)
    
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()
    
    with patch("backend.ingestion.pipeline_v2.async_session") as mock_async_session:
        mock_async_session.return_value.__aenter__.return_value = mock_session
        
        # Mock existing document with same content hash
        existing_doc = MagicMock()
        existing_doc.content_hash = "hash123"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing_doc
        mock_session.execute.return_value = mock_result
        
        await store.persist(ingestion_package)

    # Should skip persistence
    assert ingestion_package.state == IngestionState.PERSISTED
    assert ingestion_package.doc_record is None
    mock_vector_store.upsert_batch.assert_not_called()
    assert mock_session.add.call_count == 0

@pytest.mark.asyncio
async def test_knowledge_store_versioning(
    mock_vector_store, 
    ingestion_package
):
    store = KnowledgeStore(vector_store=mock_vector_store)
    
    ingestion_package.raw_doc.content_hash = "new_hash"
    
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()
    
    with patch("backend.ingestion.pipeline_v2.async_session") as mock_async_session:
        mock_async_session.return_value.__aenter__.return_value = mock_session
        
        # Mock existing document with different content hash
        existing_doc = MagicMock()
        existing_doc.content_hash = "old_hash"
        existing_doc.version = 1
        existing_doc.id = "old_doc_id"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing_doc
        mock_session.execute.return_value = mock_result
        
        await store.persist(ingestion_package)

    # Assertions
    assert existing_doc.is_active is False
    assert mock_session.execute.call_count >= 2 
    
    # Verify new version
    # The first call to add is for Document
    assert mock_session.add.call_args_list[0][0][0].version == 2
    assert mock_session.add.call_args_list[0][0][0].previous_version_id == "old_doc_id"
    
    # Verify 2 commits (one in prepare_version, one in persist)
    assert mock_session.commit.call_count == 2
