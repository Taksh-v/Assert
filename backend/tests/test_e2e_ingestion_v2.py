import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from types import SimpleNamespace

from backend.ingestion.pipeline import IngestionPipeline
from backend.ingestion.document_run import IngestionState

class MockConnector:
    def __init__(self):
        self.id = "conn-1"
        self.workspace_id = "ws-1"
        self.type = SimpleNamespace(value="slack")
        self.config = "encrypted-config"

class MockDoc:
    def __init__(self, title, content):
        self.title = title
        self.content = content
        self.source_id = f"id-{title}"
        self.source_url = f"url-{title}"
        self.source_type = "slack"
        self.metadata = {}

@pytest.mark.asyncio
async def test_ingestion_pipeline_v2_integration():
    # Mock database session and connector
    mock_connector = MockConnector()
    
    with patch("backend.ingestion.pipeline.async_session") as mock_session_factory, \
         patch("backend.ingestion.pipeline.decrypt_config") as mock_decrypt, \
         patch("backend.connectors.registry.connector_factory.create") as mock_create_conn, \
         patch("backend.observability.telemetry.Telemetry.log_failure", new_callable=AsyncMock) as mock_telemetry:

        # Setup mock session
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        # Mock connector query
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.side_effect = [mock_connector, None, None, None] # connector, sync_state, state in _persist_sync_state
        mock_session.execute.return_value = mock_result
        
        # Mock config decryption
        mock_decrypt.return_value = {"token": "fake-token"}
        
        # Mock connector implementation
        mock_conn_impl = AsyncMock()
        mock_create_conn.return_value = mock_conn_impl
        mock_conn_impl.connect.return_value = "fake-connection"
        
        async def mock_fetch_documents(*args, **kwargs):
            yield MockDoc("Doc 1", "Content 1")
            yield MockDoc("Doc 2", "Content 2")
        
        mock_conn_impl.fetch_documents = mock_fetch_documents
        
        # Initialize pipeline
        pipeline = IngestionPipeline()
        
        # Mock the runner.process to avoid hitting real DB/VectorStore/etc. in transformers
        # Actually, let's let it run but mock the transformers or the runner itself
        # to verify it was called.
        
        original_process = pipeline.runner.process
        pipeline.runner.process = AsyncMock(side_effect=original_process)
        
        # Mock transformers to avoid real work while keeping orchestration intact.
        with patch.object(pipeline.embedder, "aembed_multi", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [{"content": [0.1]}]

            with patch.object(pipeline.classifier, "classify", new_callable=AsyncMock) as mock_classify:
                mock_classify.return_value = "report"

                with patch.object(pipeline.extractor, "extract_semantic_metadata", new_callable=AsyncMock) as mock_extract:
                    mock_extract.return_value = {"summary": "sum"}

                    stats = await pipeline.run("conn-1")

                    assert stats["processed"] == 2
                    assert stats["fetched"] == 2
                    assert pipeline.runner.process.call_count == 2

                    # Verify IngestionPackage was passed to runner.process (via call_args)
                    for call in pipeline.runner.process.call_args_list:
                        args, kwargs = call
                        assert isinstance(args[0], MockDoc)
                        assert args[1] == "ws-1"
                        assert args[2] == "conn-1"

if __name__ == "__main__":
    asyncio.run(test_ingestion_pipeline_v2_integration())
