import asyncio
import os
import sys
from unittest.mock import MagicMock

# Ensure backend directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Mock passlib before any backend imports to support offline test environments
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

# Mock other external service clients to run 100% offline and fast
sys.modules["groq"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()

# Define mock raw document classes
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

# Mock SlackConnector class
class MockSlackConnector:
    async def connect(self, config):
        return "mock_connection"
        
    async def fetch_documents(self, connection, since=None, selected_ids=None):
        yield MockRawDocument("Doc 1", "Content of doc 1", "id-1", "slack://msg1")
        yield CorruptedMockRawDocument("Corrupted Doc", "id-2", "slack://msg2")
        yield MockRawDocument("Doc 3", "Content of doc 3", "id-3", "slack://msg3")

# Monkey-patch mock processors before importing IngestionPipeline to run 100% offline
import backend.ingestion.pipeline

# 1. Mock PIIScrubber
class MockPIIScrubber:
    def scrub(self, text):
        return text, []
backend.ingestion.pipeline.PIIScrubber = MockPIIScrubber

# 2. Mock Embedder
class MockEmbedder:
    def embed_multi(self, chunks, title, summary):
        return [{"content": [0.0]*384, "title": [0.0]*384, "summary": [0.0]*384} for _ in chunks]

    async def aembed_multi(self, chunks, title, summary):
        return self.embed_multi(chunks, title, summary)
backend.ingestion.pipeline.Embedder = MockEmbedder

# 3. Mock EntityExtractor
class MockEntityExtractor:
    async def extract_semantic_metadata(self, text):
        return {"entities": [], "topics": [], "keywords": [], "summary": ""}
backend.ingestion.pipeline.EntityExtractor = MockEntityExtractor

# 4. Mock DocumentClassifier
class MockDocumentClassifier:
    async def classify(self, content, filename):
        return "general"
backend.ingestion.pipeline.DocumentClassifier = MockDocumentClassifier

# 5. Mock VectorStore and GraphStore
backend.ingestion.pipeline.VectorStore.upsert_batch = MagicMock()
backend.ingestion.pipeline.GraphStore = MagicMock()
backend.ingestion.pipeline.SlackConnector = MockSlackConnector
from backend.connectors.registry import connector_registry
connector_registry.register("slack", MockSlackConnector)

# Now import core elements
from backend.core.database import init_db, close_db, async_session
from backend.models.connector import Connector, ConnectorType, ConnectorStatus
from backend.models.failed_ingestion import FailedIngestion
from backend.models.document import Document
from backend.ingestion.pipeline import IngestionPipeline
from sqlalchemy import select

async def test_ingestion_dlq_routing():
    print("🚀 Initializing test database for DLQ validation...")
    await init_db()
    
    workspace_id = "test-workspace-dlq"
    connector_id = "mock-connector-dlq-id"
    
    # 1. Create a dummy connector record and clean old test data
    async with async_session() as session:
        # Clean up old test runs
        from sqlalchemy import delete
        await session.execute(delete(Document).where(Document.workspace_id == workspace_id))
        await session.execute(delete(FailedIngestion).where(FailedIngestion.workspace_id == workspace_id))
        await session.execute(delete(Connector).where(Connector.id == connector_id))
        await session.commit()
        
        connector = Connector(
            id=connector_id,
            workspace_id=workspace_id,
            type=ConnectorType.SLACK,
            config={},  # Encrypted configuration empty dict
            status=ConnectorStatus.ACTIVE
        )
        session.add(connector)
        await session.commit()
        print("   ✅ Mock connector inserted into DB.")
            
    # 2. Run the Ingestion Pipeline
    print("🟢 Executing Ingestion Pipeline...")
    pipeline = IngestionPipeline()
    
    # Since we added error isolation, this call should complete successfully without raising errors
    await pipeline.run(connector_id=connector_id)
    print("   ✅ Ingestion pipeline executed to completion.")
    
    # 3. Assert Valid Documents are Ingested
    async with async_session() as session:
        stmt = select(Document).where(Document.workspace_id == workspace_id, Document.is_active == True)
        res = await session.execute(stmt)
        documents = res.scalars().all()
        titles = [d.title for d in documents]
        print(f"   Successfully Ingested Documents: {titles}")
        
        assert "Doc 1" in titles, "Doc 1 should be ingested"
        assert "Doc 3" in titles, "Doc 3 should be ingested"
        assert "Corrupted Doc" not in titles, "Corrupted Doc should NOT be in documents table"
        
    # 4. Assert Corrupted Document is routed to the DLQ table
    async with async_session() as session:
        stmt = select(FailedIngestion).where(FailedIngestion.workspace_id == workspace_id)
        res = await session.execute(stmt)
        failed_records = res.scalars().all()
        
        print(f"   Failed Ingestions (DLQ) Count: {len(failed_records)}")
        assert len(failed_records) == 1, f"Expected 1 failed record in DLQ, got {len(failed_records)}"
        
        failed_doc = failed_records[0]
        print(f"   Failed Document DLQ Details:")
        print(f"     URL: {failed_doc.source_url}")
        print(f"     Error Message: {failed_doc.error_message}")
        print(f"     Status: {failed_doc.status}")
        
        assert failed_doc.source_url == "slack://msg2"
        assert "ValueError" in failed_doc.error_message or "corruption" in failed_doc.error_message
        assert failed_doc.status == "pending"
        
    await close_db()
    print("🎉 DLQ Ingestion test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_ingestion_dlq_routing())
