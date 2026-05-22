import logging
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Any
from sqlalchemy import select, delete, update

from backend.models.connector import Connector, ConnectorStatus
from backend.models.document import Document
from backend.models.knowledge_object import KnowledgeObject
from backend.models.knowledge_event import KnowledgeEvent
from backend.models.chunk import Chunk as DBChunk
from backend.models.connector_sync_state import ConnectorSyncState
from backend.core.security import decrypt_config

from backend.connectors.notion import NotionConnector
from backend.connectors.google_drive import GoogleDriveConnector
from backend.connectors.slack import SlackConnector

from backend.ingestion.pii_scrubber import PIIScrubber
from backend.ingestion.normalizer import DocumentNormalizer
from backend.ingestion.chunker import DocumentChunker
from backend.ingestion.embedder import Embedder
from backend.ingestion.extractor import EntityExtractor
from backend.ingestion.classifier import DocumentClassifier
from backend.ingestion.document_parser import HybridParser
from backend.graph.graph_store import GraphStore
from backend.graph.entity_resolver import EntityResolver
from backend.core.vector_store import VectorStore
from backend.core.database import async_session, upsert_idempotent

logger = logging.getLogger(__name__)

class IngestionPipeline:
    """
    Orchestrates the ingestion of documents with semantic intelligence.
    """

    def __init__(self):
        self.normalizer = DocumentNormalizer()
        self.parser = HybridParser()
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

    def _matches_selected_id(self, raw_doc: Any, selected_ids: Optional[List[str]]) -> bool:
        """Safety filter for connectors that cannot pre-filter selected resources."""
        if not selected_ids:
            return True

        selected = {str(item) for item in selected_ids if item}
        source_id = str(getattr(raw_doc, "source_id", ""))
        metadata = getattr(raw_doc, "metadata", {}) or {}
        channel_id = str(metadata.get("channel_id", ""))

        candidates = {source_id}
        if channel_id:
            candidates.add(channel_id)
            candidates.add(f"slack-channel-{channel_id}")

        return bool(selected.intersection(candidates))

    async def _process_document(self, raw_doc: Any, workspace_id: str, connector_id: Optional[str] = None):
        """
        Processes a single document through the ingestion lifecycle.
        """
        start_time = datetime.utcnow()
        try:
            resolver = EntityResolver()
            parser = self.parser

            logger.info(f"Processing: {raw_doc.title} ({raw_doc.source_type})")

            normalized = self.normalizer.normalize_generic(
                {
                    "source_id": getattr(raw_doc, "source_id", "unknown"),
                    "document_id": getattr(raw_doc, "source_id", str(uuid.uuid4())),
                    "title": getattr(raw_doc, "title", "Untitled"),
                    "content": getattr(raw_doc, "raw_content", getattr(raw_doc, "content", "")),
                    "source_url": getattr(raw_doc, "source_url", ""),
                    "metadata": getattr(raw_doc, "metadata", {}),
                    "permissions": getattr(raw_doc, "permissions", []),
                },
                workspace_id=workspace_id,
            )
            
            # 1. Versioning & Idempotency Check
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
                    if hasattr(raw_doc, 'content_hash') and existing_doc.content_hash == raw_doc.content_hash:
                        logger.info(f"Deduplication hit: skipping {raw_doc.title}")
                        return
                    
                    logger.info(f"Versioning: Archiving v{existing_doc.version} of {raw_doc.title}")
                    existing_doc.is_active = False
                    current_version = existing_doc.version + 1
                    prev_doc_id = existing_doc.id
                    
                    await session.execute(
                        update(DBChunk)
                        .where(DBChunk.document_id == existing_doc.id)
                        .values(is_active=False)
                    )
                    await session.commit()
            
            # 2. Parsing (Multi-Modal Sensory Layer)
            raw_content = normalized.raw_content or getattr(raw_doc, "raw_content", getattr(raw_doc, "content", ""))
            content_format = getattr(raw_doc, "content_format", "text")
            file_name = getattr(raw_doc, "title", "document")
            if hasattr(raw_doc, "source_url") and "." in raw_doc.source_url:
                file_name = raw_doc.source_url.split("/")[-1]

            # Use HybridParser for actual multi-modal extraction if it's not simple text
            if isinstance(raw_content, bytes) or (isinstance(raw_content, str) and len(raw_content) < 1000 and any(raw_content.lower().endswith(ext) for ext in [".pdf", ".png", ".jpg", ".mp3"])):
                content_bytes = raw_content if isinstance(raw_content, bytes) else raw_content.encode()
                elements = await parser.parse_bytes(content_bytes, file_name)
            elif content_format == "html":
                elements = parser._parse_html_string(raw_content)
            else:
                elements = [{"type": "text", "content": raw_content, "metadata": {}}]

            if not elements:
                 elements = [{"type": "text", "content": str(raw_content), "metadata": {}}]

            # 3. PII Scrubbing
            scrubbed_elements = []
            for el in elements:
                scrubbed_text, _ = self.scrubber.scrub(el["content"])
                el["content"] = scrubbed_text
                scrubbed_elements.append(el)
            
            full_text = "\n\n".join([el["content"] for el in scrubbed_elements])
            tier = getattr(raw_doc, "tier", 2)
            doc_title = normalized.title or raw_doc.title
            doc_type = await self.classifier.classify(full_text, doc_title)
            
            # 4. Metadata Enrichment
            enriched_metadata = {"entities": [], "topics": [], "keywords": [], "summary": "", "events": []}
            if self.extractor:
                try:
                    logger.info(f"Enriching metadata for: {doc_title}")
                    raw_metadata = await self.extractor.extract_semantic_metadata(full_text)
                    enriched_metadata.update(raw_metadata)
                    
                    # Scrub PII from metadata
                    enriched_metadata["summary"], _ = self.scrubber.scrub(enriched_metadata.get("summary", ""))
                except Exception as e:
                    logger.warning(f"Semantic enrichment failed: {e}")
            
            # 5. Entity Resolution
            extracted_entities = enriched_metadata.get("entities", [])
            resolved_entities = []
            if extracted_entities:
                async with async_session() as session:
                    resolved_entities = await resolver.resolve_and_link(
                        session=session,
                        workspace_id=workspace_id,
                        document_id=str(uuid.uuid4()),
                        entities=extracted_entities
                    )

            # 6. Chunking
            chunks_data = self.chunker.chunk_elements(scrubbed_elements, doc_type="auto")
            chunks = [c["content"] for c in chunks_data]
            
            # 7. Database Record
            async with async_session() as session:
                doc_record = Document(
                    workspace_id=workspace_id,
                    connector_id=connector_id,
                    source_url=raw_doc.source_url,
                    title=raw_doc.title,
                    document_type=doc_type,
                    content_hash=getattr(raw_doc, "content_hash", str(hash(raw_content))),
                    chunk_count=len(chunks),
                    tier=tier,
                    tags=enriched_metadata.get("keywords", []),
                    version=current_version,
                    previous_version_id=prev_doc_id,
                    is_active=True
                )
                doc_record = await session.merge(doc_record)
                await session.commit()
                await session.refresh(doc_record)

            # 8. Vector Storage
            multi_embeddings = self.embedder.embed_multi(
                chunks=chunks,
                title=raw_doc.title,
                summary=enriched_metadata.get("summary", "")
            )
            
            payloads = [
                {
                    "title": raw_doc.title,
                    "source_url": raw_doc.source_url,
                    "source_type": raw_doc.source_type,
                    "content_tier": tier,
                    "extracted_entities": [e["name"] for e in (resolved_entities or extracted_entities)],
                    "summary": enriched_metadata.get("summary", ""),
                    "version": current_version,
                    "is_active": True
                }
                for i in range(len(chunks))
            ]
            
            self.vector_store.upsert_batch(workspace_id, multi_embeddings, payloads)

            # 9. Chunk Storage
            async with async_session() as session:
                for idx, chunk_text in enumerate(chunks):
                    c_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_record.id}:{idx}"))
                    payload = payloads[idx]
                    new_chunk = DBChunk(
                        id=c_id,
                        document_id=doc_record.id,
                        workspace_id=workspace_id,
                        content=chunk_text,
                        chunk_index=idx,
                        tier=payload.get("content_tier", 2),
                        source_type=payload.get("source_type"),
                        source_url=payload.get("source_url"),
                        document_title=payload.get("title"),
                        version=current_version,
                        is_active=True
                    )
                    await session.merge(new_chunk)
                await session.commit()
            
            # 10. Graph & Event Storage
            if self.graph_store:
                try:
                    self.graph_store.add_document_node(workspace_id, doc_record.id, raw_doc.title, raw_doc.source_url)
                    if resolved_entities:
                        self.graph_store.add_entities_and_relationships(doc_record.id, resolved_entities)
                    
                    extracted_events = enriched_metadata.get("events", [])
                    if extracted_events:
                        async with async_session() as session:
                            for event_data in extracted_events:
                                new_event = KnowledgeEvent(
                                    workspace_id=workspace_id,
                                    event_type=event_data.get("type", "milestone"),
                                    title=event_data.get("title", "Unknown Event"),
                                    description=event_data.get("description"),
                                    timestamp=datetime.utcnow(),
                                    source_document_id=doc_record.id,
                                    metadata_json=event_data
                                )
                                session.add(new_event)
                                self.graph_store.add_event_node(doc_record.id, event_data)
                            await session.commit()
                except Exception as ge:
                    logger.warning(f"Graph storage failed: {ge}")
            
            logger.info(f"✅ Finished Ingestion: {doc_title}")
            
        except Exception as e:
            logger.error(f"Error processing document {raw_doc.title}: {e}")
            raise e

    async def _persist_sync_state(
        self,
        connector_id: str,
        workspace_id: str,
        stats: dict,
        last_error: Optional[str] = None,
    ) -> None:
        """Persist sync metadata so later runs can incrementally resume."""
        async with async_session() as session:
            stmt = select(ConnectorSyncState).where(
                ConnectorSyncState.connector_id == connector_id,
                ConnectorSyncState.workspace_id == workspace_id,
            )
            result = await session.execute(stmt)
            state = result.scalars().first()

            now = datetime.utcnow()
            if not state:
                state = ConnectorSyncState(
                    connector_id=connector_id,
                    workspace_id=workspace_id,
                )
                session.add(state)

            if last_error:
                state.last_error = last_error
                await session.execute(
                    update(Connector)
                    .where(Connector.id == connector_id)
                    .values(
                        status=ConnectorStatus.ERROR,
                        error_log={"last_error": last_error, "timestamp": now.isoformat()},
                    )
                )
            else:
                state.last_sync_at = now
                state.last_sync_token = None
                state.last_error = None

                await session.execute(
                    update(Connector)
                    .where(Connector.id == connector_id)
                    .values(status=ConnectorStatus.ACTIVE, last_synced_at=now)
                )

            state.last_stats = stats
            state.updated_at = now
            await session.commit()

    async def run(self, connector_id: str, selected_ids: Optional[List[str]] = None):
        """
        Run the ingestion pipeline for a connector.
        """
        stats = {
            "connector_id": connector_id,
            "processed": 0,
            "failed": 0,
            "fetched": 0,
            "skipped_selected": 0,
            "run_started_at": datetime.utcnow().isoformat(),
        }
        async with async_session() as session:
            stmt = select(Connector).where(Connector.id == connector_id)
            connector = (await session.execute(stmt)).scalars().first()
            if not connector: 
                logger.error(f"Connector {connector_id} not found")
                return

            sync_stmt = select(ConnectorSyncState).where(
                ConnectorSyncState.connector_id == connector_id,
                ConnectorSyncState.workspace_id == connector.workspace_id,
            )
            sync_state = (await session.execute(sync_stmt)).scalars().first()
            since = None
            if sync_state and sync_state.last_sync_at:
                since = sync_state.last_sync_at - timedelta(minutes=5)

            # Decrypt configuration for connection
            try:
                config = decrypt_config(connector.config)
            except Exception as e:
                logger.error(f"Failed to decrypt config for connector {connector_id}: {e}")
                return

            connector_type = getattr(connector.type, "value", connector.type)
            workspace_id = connector.workspace_id

            # Initialize connector implementation dynamically
            try:
                from backend.connectors.registry import connector_registry
                conn_class = connector_registry.get_connector(connector_type)
                conn_impl = conn_class()
            except ValueError as e:
                logger.error(f"Unsupported connector type: {connector_type} - {e}")
                return

            try:
                connection = await conn_impl.connect(config)
                
                # Fetch documents and process concurrently with error isolation
                semaphore = asyncio.Semaphore(5)  # Cap concurrency to 5 parallel documents
                tasks_list = []
                
                from backend.observability.telemetry import Telemetry

                async def process_with_boundary(doc_obj):
                    async with semaphore:
                        try:
                            await self._process_document(doc_obj, workspace_id, connector_id)
                            return True
                        except Exception as doc_error:
                            stats["failed"] += 1
                            logger.warning(f"Error processing document {getattr(doc_obj, 'title', 'unknown')}: {doc_error}")
                            
                            # Safe retrieval of content in case it raises an exception
                            try:
                                raw_content = getattr(doc_obj, "raw_content", getattr(doc_obj, "content", ""))
                                content_snippet = str(raw_content)[:2000] if raw_content else ""
                            except Exception:
                                content_snippet = "<UNREADABLE: error retrieving content>"
                                
                            raw_payload = {
                                "title": getattr(doc_obj, "title", "unknown"),
                                "source_id": getattr(doc_obj, "source_id", "unknown"),
                                "source_url": getattr(doc_obj, "source_url", "unknown"),
                                "source_type": getattr(doc_obj, "source_type", "unknown"),
                                "content": content_snippet
                            }
                            await Telemetry.log_failure(
                                workspace_id=workspace_id,
                                source_type=connector_type,
                                source_url=getattr(doc_obj, "source_url", "unknown"),
                                error=doc_error,
                                raw_payload=raw_payload
                            )
                            logger.warning(f"Skipping corrupted document {getattr(doc_obj, 'title', 'Unknown')} and continuing: {doc_error}")
                            return False

                async for raw_doc in conn_impl.fetch_documents(
                    connection,
                    since=since,
                    selected_ids=selected_ids,
                ):
                    # Filter by selected_ids if provided
                    if not self._matches_selected_id(raw_doc, selected_ids):
                        stats["skipped_selected"] += 1
                        continue
                    stats["fetched"] += 1
                    tasks_list.append(asyncio.create_task(process_with_boundary(raw_doc)))
                
                if tasks_list:
                    results = await asyncio.gather(*tasks_list)
                    stats["processed"] = sum(1 for result in results if result)
                
                stats["run_completed_at"] = datetime.utcnow().isoformat()
                await self._persist_sync_state(
                    connector_id=connector_id,
                    workspace_id=workspace_id,
                    stats=stats,
                )
                logger.info(f"Sync completed for connector {connector_id}")
                return stats
            except Exception as e:
                logger.error(f"Sync failed for connector {connector_id}: {e}")
                stats["run_completed_at"] = datetime.utcnow().isoformat()
                await self._persist_sync_state(
                    connector_id=connector_id,
                    workspace_id=workspace_id,
                    stats=stats,
                    last_error=str(e),
                )
                raise e

    def close(self):
        if self.graph_store:
            self.graph_store.close()
