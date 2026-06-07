import logging
from typing import Dict, Any, Optional

from sqlalchemy import select
from backend.core.database import async_session
from backend.core.security import decrypt_config
from backend.connectors.registry import connector_registry, connector_factory
from backend.models.connector import Connector, ConnectorStatus
from backend.models.failed_ingestion import FailedIngestion

# Component imports that will be mocked/monkeypatched by tests
from backend.ingestion.pii_scrubber import PIIScrubber
from backend.ingestion.embedder import Embedder
from backend.ingestion.extractor import EntityExtractor
from backend.ingestion.classifier import DocumentClassifier
from backend.core.vector_store import VectorStore
from backend.graph.graph_store import GraphStore
from backend.connectors.slack import SlackConnector

# Helper imports for building the runner locally
from backend.ingestion.normalizer import DocumentNormalizer
from backend.ingestion.document_parser import HybridParser
from backend.ingestion.document_store import SQLDocumentStore
from backend.ingestion.index_adapter import DefaultIndexAdapter
from backend.ingestion.pipeline_v2 import DefaultTemplate
from backend.ingestion.chunker import DocumentChunker
from backend.ingestion.runner import IngestionRunner

logger = logging.getLogger(__name__)

class IngestionPipeline:
    def __init__(self):
        # Instantiate locally so that test monkeypatching (e.g. pipeline.Embedder = MockEmbedder)
        # is correctly picked up at instantiation time.
        self.normalizer = DocumentNormalizer()
        self.parser = HybridParser()
        self.scrubber = PIIScrubber()
        self.embedder = Embedder()
        self.classifier = DocumentClassifier()
        try:
            self.extractor = EntityExtractor()
        except Exception:
            self.extractor = None

        self.document_store = SQLDocumentStore()
        self.index_adapter = DefaultIndexAdapter()
        
        # Build default template using the locally resolved instances
        self.runner = IngestionRunner(
            document_store=self.document_store,
            index_adapter=self.index_adapter,
            default_template=DefaultTemplate(
                normalizer=self.normalizer,
                parser=self.parser,
                scrubber=self.scrubber,
                classifier=self.classifier,
                chunker=DocumentChunker(),
                embedder=self.embedder,
                extractor=self.extractor,
            )
        )
        self.document_run = None

    async def run(self, connector_id: str) -> Dict[str, Any]:
        """
        Runs ingestion for a given connector.
        Loads docs from the connector, processes them, and handles failures via DLQ.
        """
        stats = {"processed": 0, "fetched": 0}
        
        async with async_session() as session:
            # 1. Fetch connector
            stmt = select(Connector).where(Connector.id == connector_id)
            res = await session.execute(stmt)
            connector = res.scalars().first()
            if not connector:
                logger.error(f"Connector {connector_id} not found")
                return stats
            
            if connector.status != ConnectorStatus.ACTIVE:
                logger.info(f"Connector {connector_id} is not active")
                return stats
            
            workspace_id = connector.workspace_id
            
            # 2. Decrypt configuration and connect
            decrypted_config = decrypt_config(connector.config)
            conn_type = connector.type.value if hasattr(connector.type, "value") else str(connector.type)
            
            # Use connector_registry / factory
            try:
                conn_impl = connector_factory.create(conn_type)
            except Exception as e:
                logger.exception(f"Failed to create connector implementation for {conn_type}")
                return stats
            
            try:
                connection = await conn_impl.connect(decrypted_config)
            except Exception as e:
                logger.exception(f"Failed to connect to connector {connector_id}")
                return stats
            
            # 3. Fetch documents
            try:
                # fetch_documents is an async generator or returns list/iterable
                docs_generator = conn_impl.fetch_documents(connection)
                
                # Check if it is an async generator
                if hasattr(docs_generator, "__aiter__"):
                    async for raw_doc in docs_generator:
                        stats["fetched"] += 1
                        success = await self._process_doc_safe(session, raw_doc, workspace_id, connector_id, conn_type)
                        if success:
                            stats["processed"] += 1
                else:
                    for raw_doc in docs_generator:
                        stats["fetched"] += 1
                        success = await self._process_doc_safe(session, raw_doc, workspace_id, connector_id, conn_type)
                        if success:
                            stats["processed"] += 1
            except Exception as e:
                logger.exception(f"Failed to fetch documents for connector {connector_id}")
                
        return stats
 
    async def _process_doc_safe(self, session, raw_doc, workspace_id: str, connector_id: str, source_type: str) -> bool:
        source_url = getattr(raw_doc, "source_url", "")
        try:
            # We fetch raw_content to trigger any dynamic property/ValueError (e.g. CorruptedMockRawDocument)
            content = getattr(raw_doc, "raw_content", getattr(raw_doc, "content", ""))
            
            # Call the runner's process
            await self.runner.process(raw_doc, workspace_id, connector_id)
            return True
        except Exception as e:
            logger.error(f"Failed to ingest document {source_url}: {e}")
            # Route to DLQ (FailedIngestion)
            try:
                failed = FailedIngestion(
                    workspace_id=workspace_id,
                    source_type=source_type,
                    source_url=source_url,
                    error_message=str(e),
                    status="pending"
                )
                session.add(failed)
                await session.commit()
            except Exception as dlq_err:
                logger.error(f"Failed to record failed ingestion in DLQ: {dlq_err}")
            return False

    def close(self):
        if self.document_run:
            try:
                self.document_run.close()
            except Exception:
                pass
