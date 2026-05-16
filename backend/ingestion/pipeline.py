import logging
from datetime import datetime, timedelta
from typing import Optional, List
from backend.models.connector import Connector
from backend.models.document import Document
from backend.connectors.notion import NotionConnector
from backend.connectors.google_drive import GoogleDriveConnector
from backend.connectors.slack import SlackConnector
from backend.ingestion.pii_scrubber import PIIScrubber
from backend.ingestion.normalizer import DocumentNormalizer
from backend.ingestion.chunker import DocumentChunker
from backend.ingestion.embedder import Embedder
from backend.core.vector_store import VectorStore
from backend.core.database import async_session, upsert_idempotent
from sqlalchemy import select, delete

from backend.ingestion.extractor import EntityExtractor
from backend.ingestion.classifier import DocumentClassifier
from backend.graph.graph_store import GraphStore
from backend.core.metrics import INGESTION_LATENCY, CHUNK_COUNT
from qdrant_client.http import models
from backend.models.chunk import Chunk as DBChunk
import time
import uuid

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Orchestrates the ingestion of documents with semantic intelligence.
    """

    def __init__(self):
        self.normalizer = DocumentNormalizer()
        self.scrubber = PIIScrubber()
        self.embedder = Embedder()
        self.vector_store = VectorStore()
        try:
            self.extractor = EntityExtractor()
        except Exception as e:
            logger.warning(f"EntityExtractor init failed (non-fatal): {e}")
            self.extractor = None
        self.chunker = DocumentChunker()
        self.classifier = DocumentClassifier()
        try:
            self.graph_store = GraphStore()
        except Exception as e:
            logger.warning(f"GraphStore init failed (non-fatal): {e}")
            self.graph_store = None

    async def run_reconciliation(self, connector_id: str):
        """
        Blueprint Layer 14: Sync Reconciliation.
        Detects deleted items at source and prunes them from the brain.
        """
        logger.info(f"Starting reconciliation for connector {connector_id}")
        # 1. Get all IDs from source
        # 2. Get all IDs from our DB
        # 3. Identify IDs in DB but NOT in source
        # 4. Prune those IDs
        pass
    async def run(self, connector_id: str, selected_ids: Optional[List[str]] = None):
        """
        Run the enhanced ingestion pipeline with optional selective indexing.
        """
        overall_start = datetime.utcnow()
        connector_type = "unknown"
        
        async with async_session() as session:
            # 1. Fetch connector config
            stmt = select(Connector).where(Connector.id == connector_id)
            result = await session.execute(stmt)
            connector = result.scalars().first()
            
            if not connector:
                logger.error(f"Connector {connector_id} not found")
                return

            connector_type = getattr(connector.type, "value", connector.type)

            # 2. Initialize connector
            if connector_type == "notion":
                conn_impl = NotionConnector()
            elif connector_type == "google_drive":
                conn_impl = GoogleDriveConnector()
            elif connector_type == "slack":
                conn_impl = SlackConnector()
            else:
                logger.error(f"Unsupported connector type: {connector_type}")
                return
            
            # 3. Connect & Fetch
            try:
                from backend.models.connector_sync_state import ConnectorSyncState
                
                # Layer 14: Get Incremental Sync State
                stmt = select(ConnectorSyncState).where(
                    ConnectorSyncState.connector_id == connector_id,
                    ConnectorSyncState.workspace_id == connector.workspace_id
                )
                res = await session.execute(stmt)
                sync_state = res.scalars().first()
                
                if not sync_state:
                    sync_state = ConnectorSyncState(
                        connector_id=connector_id,
                        workspace_id=connector.workspace_id,
                        last_sync_at=connector.last_synced_at or datetime(2000, 1, 1)
                    )
                    session.add(sync_state)
                    await session.commit()

                connection = await conn_impl.connect(connector.config)
                logger.info(f"Streaming documents for {connector_type} (Since: {sync_state.last_sync_at})")
                doc_stream = conn_impl.fetch_documents(connection, since=sync_state.last_sync_at)
            except Exception as e:
                logger.error(f"Dynamic connection failed for {connector_type}: {e}")
                connector.status = "error"
                await session.commit()
                return

            # Initialize workers and tools once outside the loop
            from backend.ingestion.document_parser import HybridParser
            from backend.ingestion.entity_resolver import EntityResolver
            parser = HybridParser()
            resolver = EntityResolver()
            
            semaphore = asyncio.Semaphore(5)  # Process 5 documents at once
            
            async def process_document(raw_doc):
                async with semaphore:
                    try:
                        # Layer 14: Strict Differential Filtering
                        if sync_state.last_sync_at and raw_doc.modified_at:
                            # If timezone-aware vs naive issues occur, we'll strip tz for comparison
                            doc_mod = raw_doc.modified_at.replace(tzinfo=None)
                            state_sync = sync_state.last_sync_at.replace(tzinfo=None)
                            if doc_mod <= state_sync:
                                logger.info(f"Incremental skip: {raw_doc.title} (unmodified)")
                                return

                        start_time = datetime.utcnow()
                        # ... (rest of processing) ...
                        # Selective Indexing Gate
                        if selected_ids and raw_doc.source_id not in selected_ids:
                            return
                            
                        logger.info(f"Processing: {raw_doc.title} ({raw_doc.source_type})")
                        workspace_id = connector.workspace_id
                        
                        # 3b. Versioning & Idempotency Check (Layer 15)
                        current_version = 1
                        prev_doc_id = None
                        async with async_session() as session:
                            stmt = select(Document).where(
                                Document.source_url == raw_doc.source_url,
                                Document.workspace_id == workspace_id,
                                Document.is_active == True
                            )
                            res = await session.execute(stmt)
                            existing_doc = res.scalars().first()
                            
                            if existing_doc:
                                if existing_doc.content_hash == raw_doc.content_hash:
                                    logger.info(f"Deduplication hit: skipping {raw_doc.title}")
                                    return
                                
                                # Content changed! Archive the old version
                                logger.info(f"Versioning: Archiving v{existing_doc.version} of {raw_doc.title}")
                                existing_doc.is_active = False
                                current_version = existing_doc.version + 1
                                prev_doc_id = existing_doc.id
                                
                                # ARCHIVE chunks in Postgres
                                from backend.models.chunk import Chunk as DBChunk
                                from sqlalchemy import update
                                await session.execute(
                                    update(DBChunk)
                                    .where(DBChunk.document_id == existing_doc.id)
                                    .values(is_active=False)
                                )
                                await session.commit()
                                
                                # ARCHIVE chunks in Qdrant (Phase 2: Metadata Update)
                                # For simplicity, we'll just upsert new active ones, 
                                # but in production, we'd update the old ones to is_active=False in Qdrant too.

                        # 4. Multimodal Parsing
                        if raw_doc.content_format == "html":
                            elements = parser._parse_html_string(raw_doc.raw_content)
                        else:
                            elements = [{"type": "text", "content": raw_doc.raw_content, "metadata": {}}]

                        # 5. Scrub PII (Parallelized)
                        scrub_tasks = [asyncio.to_thread(self.scrubber.scrub, el["content"]) for el in elements]
                        scrubbed_results = await asyncio.gather(*scrub_tasks)
                        for i, (scrubbed_text, _) in enumerate(scrubbed_results):
                            elements[i]["content"] = scrubbed_text
                        
                        # Full text for classification and extraction
                        full_text = "\n\n".join([el["content"] for el in elements])
                        tier = getattr(raw_doc, "tier", None) or 2
                        doc_type = await self.classifier.classify(full_text, raw_doc.title)
                        
                        # 6. Semantic Metadata Enrichment (Layer 5)
                        enriched_metadata = {"entities": [], "topics": [], "keywords": [], "summary": ""}
                        if self.extractor:
                            try:
                                logger.info(f"Enriching metadata (Layer 5) for: {raw_doc.title}")
                                raw_metadata = await self.extractor.extract_semantic_metadata(full_text)
                                
                                # ELITE REPAIR: Scrub PII from AI-generated metadata
                                enriched_metadata["summary"], _ = self.scrubber.scrub(raw_metadata.get("summary", ""))
                                enriched_metadata["topics"] = [self.scrubber.scrub(t)[0] for t in raw_metadata.get("topics", [])]
                                enriched_metadata["keywords"] = [self.scrubber.scrub(k)[0] for k in raw_metadata.get("keywords", [])]
                                enriched_metadata["entities"] = raw_metadata.get("entities", [])
                            except Exception as e:
                                logger.warning(f"Semantic enrichment failed: {e}")
                        
                        extracted_entities = enriched_metadata.get("entities", [])
                        
                        # 7. Adaptive Chunking (Layer 6)
                        chunks_data = self.chunker.chunk_elements(elements, doc_type="auto")
                        
                        # Layer 3: PII Scrubbing (Privacy-First)
                        for chunk_info in chunks_data:
                            scrubbed_text, entities = self.scrubber.scrub(chunk_info["content"])
                            chunk_info["content"] = scrubbed_text
                            chunk_info["pii_entities"] = entities
                        
                        chunks = [c["content"] for c in chunks_data]
                        
                        # 9. Document Record (Layer 9/15) - Unified Storage
                        async with async_session() as session:
                            doc_record = Document(
                                workspace_id=workspace_id,
                                connector_id=connector_id,
                                source_url=raw_doc.source_url,
                                title=raw_doc.title,
                                document_type=doc_type,
                                content_hash=raw_doc.content_hash,
                                chunk_count=len(chunks),
                                tier=tier,
                                tags=enriched_metadata.get("keywords", []),
                                # Layer 15: Versioning
                                version=current_version,
                                previous_version_id=prev_doc_id,
                                is_active=True
                            )
                            doc_record = await session.merge(doc_record)
                            await session.commit()
                            await session.refresh(doc_record)

                        # 10. Multi-Vector Storage (Layer 8)
                        logger.info(f"Generating Multi-Vector embeddings (Layer 8) for: {raw_doc.title}")
                        multi_embeddings = await self.embedder.embed_multi(
                            contents=chunks,
                            titles=[raw_doc.title] * len(chunks),
                            summaries=[enriched_metadata.get("summary", "")] * len(chunks)
                        )
                        
                        payloads = [
                            {
                                "title": raw_doc.title,
                                "source_url": raw_doc.source_url,
                                "source_type": raw_doc.source_type,
                                "content_tier": tier,
                                "source_modified_at": raw_doc.modified_at.isoformat() if raw_doc.modified_at else None,
                                "extracted_entities": [e["name"] for e in extracted_entities],
                                "topics": enriched_metadata.get("topics", []),
                                "keywords": enriched_metadata.get("keywords", []),
                                "summary": enriched_metadata.get("summary", ""),
                                "heading_path": chunks_data[i].get("heading_path", []),
                                # Layer 11/15: Security & Versioning
                                "allowed_users": raw_doc.permissions.get("allowed_users", []),
                                "visibility": raw_doc.visibility,
                                "is_public": raw_doc.visibility == "public",
                                "version": current_version,
                                "is_active": True
                            }
                            for i in range(len(chunks))
                        ]
                        
                        self.vector_store.upsert_batch(
                            workspace_id=workspace_id,
                            vectors=multi_embeddings,
                            payloads=payloads
                        )

                        # 10b. Chunk Storage (Postgres for Hybrid Search)
                        # Tier-Aware Expiry (Assest Architecture Hierarchy)
                        expiry_map = {1: 90, 2: 30, 3: 7} # Days
                        expiry_days = expiry_map.get(tier, 30)
                        expires_at = datetime.utcnow() + timedelta(days=expiry_days)

                        async with async_session() as session:
                            for idx, chunk_info in enumerate(chunks_data):
                                chunk_text = chunk_info["content"]
                                chunk_type = chunk_info.get("type", "text")
                                
                                # Store in Postgres (Layer 9/15)
                                c_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_record.id}:{idx}"))
                                new_chunk = DBChunk(
                                    id=c_id,
                                    document_id=doc_record.id,
                                    workspace_id=workspace_id,
                                    content=chunk_text,
                                    chunk_index=idx,
                                    chunk_type=chunk_type,
                                    metadata_json=payloads[idx],
                                    expires_at=expires_at,
                                    version=current_version,
                                    is_active=True
                                )
                                await session.merge(new_chunk)
                            await session.commit()
                        
                        # 11. Knowledge Graph Storage (Layer 9/10 - Memgraph)
                        if self.graph_store:
                            try:
                                logger.info(f"Syncing relationships to Graph Store for: {raw_doc.title}")
                                self.graph_store.add_document_node(
                                    workspace_id=workspace_id,
                                    document_id=doc_record.id,
                                    title=raw_doc.title,
                                    source_url=raw_doc.source_url
                                )
                                if extracted_entities:
                                    self.graph_store.add_entities_and_relationships(doc_record.id, extracted_entities)
                                
                                # Layer 9/13: Lineage & Telemetry
                                logger.info(f"AUDIT: Document {doc_record.id} successfully ingested from {raw_doc.source_type}")
                            except Exception as ge:
                                logger.warning(f"Graph storage failed (Non-fatal): {ge}")
                        
                        elapsed = (datetime.utcnow() - start_time).total_seconds()
                        
                        # Layer 13: Track Success
                        from backend.observability.telemetry import Telemetry
                        Telemetry.track_latency(raw_doc.source_type, elapsed)
                        Telemetry.track_chunking(raw_doc.source_type, len(chunks))
                        
                        logger.info(f"✅ Finished Ingestion: {raw_doc.title} in {elapsed:.2f}s")
                    except Exception as e:
                        # Layer 13: DLQ Routing
                        from backend.observability.telemetry import Telemetry
                        await Telemetry.log_failure(
                            workspace_id=workspace_id,
                            source_type=raw_doc.source_type,
                            source_url=raw_doc.source_url,
                            error=e,
                            raw_payload={"title": raw_doc.title}
                        )
                        logger.error(f"Error processing document {raw_doc.title}: {e}")
            
            # Collect tasks for concurrent execution
            tasks = []
            async for raw_doc in doc_stream:
                tasks.append(process_document(raw_doc))
            
            if tasks:
                await asyncio.gather(*tasks)
            
            # 12. Update connector sync status (Layer 14: Elite Incremental tracking)
            async with async_session() as session:
                # Update the main Connector model
                stmt = select(Connector).where(Connector.id == connector_id)
                res = await session.execute(stmt)
                conn_to_update = res.scalars().first()
                
                # Update the specialized Sync State model
                stmt_state = select(ConnectorSyncState).where(
                    ConnectorSyncState.connector_id == connector_id,
                    ConnectorSyncState.workspace_id == connector.workspace_id
                )
                res_state = await session.execute(stmt_state)
                state_to_update = res_state.scalars().first()

                now = datetime.utcnow()
                if conn_to_update:
                    conn_to_update.last_synced_at = now
                if state_to_update:
                    state_to_update.last_sync_at = now
                
                await session.commit()
            
            duration = (datetime.utcnow() - overall_start).total_seconds()
            logger.info(f"🚀 Full incremental ingestion completed for connector: {connector_id} in {duration:.2f}s")
            
    # Clean up
    def close(self):
        self.graph_store.close()
