import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, update

from backend.core.database import async_session
from backend.core.vector_store import VectorStore
from backend.graph.entity_resolver import EntityResolver
from backend.graph.graph_store import GraphStore
from backend.ingestion.chunker import DocumentChunker
from backend.ingestion.classifier import DocumentClassifier
from backend.ingestion.document_parser import HybridParser
from backend.ingestion.embedder import Embedder
from backend.ingestion.extractor import EntityExtractor
from backend.ingestion.normalizer import DocumentNormalizer
from backend.ingestion.pii_scrubber import PIIScrubber
from backend.models.chunk import Chunk as DBChunk
from backend.models.document import Document
from backend.models.knowledge_event import KnowledgeEvent
from backend.ingestion.document_store import DocumentStore, SQLDocumentStore, VersionPlan
from backend.ingestion.contextualizer import ChunkContextualizer

logger = logging.getLogger(__name__)
DEFAULT_EXTRACTOR = object()


from enum import Enum, auto

class IngestionState(Enum):
    RAW = auto()
    NORMALIZED = auto()
    PARSED = auto()
    SCRUBBED = auto()
    ENRICHED = auto()
    CHUNKED = auto()
    PERSISTED = auto()
    FAILED = auto()

class IllegalStateTransition(Exception):
    pass

@dataclass
class IngestionPackage:
    raw_doc: Any
    workspace_id: str
    connector_id: Optional[str] = None
    state: IngestionState = IngestionState.RAW
    
    # Enriched data
    title: Optional[str] = None
    content: Optional[str] = None
    elements: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)
    embeddings: list[dict[str, list[float]]] = field(default_factory=list)
    doc_record: Any = None
    
    def set_normalized(self, title: str, content: str, metadata: dict[str, Any]):
        self.title = title
        self.content = content
        self.metadata.update(metadata)
        self.state = IngestionState.NORMALIZED

    def set_elements(self, elements: list[dict[str, Any]]):
        self.elements = elements
        self.state = IngestionState.PARSED

    def set_scrubbed(self, elements: list[dict[str, Any]]):
        self.elements = elements
        self.state = IngestionState.SCRUBBED

    def set_classified(self, doc_type: str):
        self.metadata["document_type"] = doc_type
        self.state = IngestionState.ENRICHED

    def set_enriched(self, metadata: dict[str, Any]):
        self.metadata.update(metadata)
        self.state = IngestionState.ENRICHED

    def set_chunks(self, chunks: list[str]):
        if self.state not in [IngestionState.NORMALIZED, IngestionState.PARSED, IngestionState.SCRUBBED, IngestionState.ENRICHED]:
            raise IllegalStateTransition(f"Cannot chunk from state {self.state}")
        self.chunks = chunks
        self.state = IngestionState.CHUNKED

    def set_embeddings(self, embeddings: list[dict[str, list[float]]]):
        self.embeddings = embeddings

@dataclass
class DocumentIngestionResult:
    status: str
    document_id: Optional[str] = None
    version: Optional[int] = None
    chunk_count: int = 0
    warnings: list[str] = field(default_factory=list)


class DocumentIngestionError(Exception):
    def __init__(self, message: str, failure_snapshot: dict[str, Any]):
        super().__init__(message)
        self.failure_snapshot = failure_snapshot


@dataclass
# DocumentStore and SQLDocumentStore extracted to backend.ingestion.document_store


class VectorIndex:
    def __init__(self, vector_store: Optional[VectorStore] = None):
        self.vector_store = vector_store or VectorStore()

    def upsert_batch(
        self,
        workspace_id: str,
        multi_embeddings: list[dict[str, list[float]]],
        payloads: list[dict[str, Any]],
    ) -> None:
        self.vector_store.upsert_batch(workspace_id, multi_embeddings, payloads)


class GraphIndex:
    def __init__(self, graph_store: Optional[GraphStore] = None):
        self.graph_store = graph_store
        if self.graph_store is None:
            self.graph_store = GraphStore()

    def add_document_artifacts(
        self,
        workspace_id: str,
        document_id: str,
        title: str,
        source_url: str,
        resolved_entities: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> None:
        if not self.graph_store:
            return

        if hasattr(self.graph_store, "_add_document_node_blocking"):
            self.graph_store._add_document_node_blocking(workspace_id, document_id, title, source_url)
        else:
            self.graph_store.add_document_node(workspace_id, document_id, title, source_url)

        if resolved_entities:
            if hasattr(self.graph_store, "_add_entities_and_relationships_blocking"):
                self.graph_store._add_entities_and_relationships_blocking(document_id, resolved_entities)
            else:
                self.graph_store.add_entities_and_relationships(document_id, resolved_entities)

        for event_data in events:
            if hasattr(self.graph_store, "_add_event_node_blocking"):
                self.graph_store._add_event_node_blocking(document_id, event_data)
            else:
                self.graph_store.add_event_node(document_id, event_data)

    def close(self) -> None:
        if self.graph_store:
            self.graph_store.close()


class NullGraphIndex:
    def add_document_artifacts(
        self,
        workspace_id: str,
        document_id: str,
        title: str,
        source_url: str,
        resolved_entities: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> None:
        return None

    def close(self) -> None:
        return None


class DocumentIngestionRun:
    """
    Single-document Company Brain lifecycle.
    """

    def __init__(
        self,
        *,
        normalizer: Optional[DocumentNormalizer] = None,
        parser: Optional[HybridParser] = None,
        scrubber: Optional[PIIScrubber] = None,
        embedder: Optional[Embedder] = None,
        extractor: Any = DEFAULT_EXTRACTOR,
        chunker: Optional[DocumentChunker] = None,
        classifier: Optional[DocumentClassifier] = None,
        document_store: Optional[DocumentStore] = None,
        vector_index: Optional[VectorIndex] = None,
        graph_index: Optional[GraphIndex] = None,
        entity_resolver_factory: Any = EntityResolver,
    ):
        self.normalizer = normalizer or DocumentNormalizer()
        self.parser = parser or HybridParser()
        self.scrubber = scrubber or PIIScrubber()
        self.embedder = embedder or Embedder()
        self.extractor = extractor
        if self.extractor is DEFAULT_EXTRACTOR:
            try:
                self.extractor = EntityExtractor()
            except Exception as e:
                logger.warning("EntityExtractor init failed (non-fatal): %s", e)
                self.extractor = None
        self.chunker = chunker or DocumentChunker()
        self.classifier = classifier or DocumentClassifier()
        self.document_store = document_store or SQLDocumentStore()
        self.vector_index = vector_index or VectorIndex()
        self.graph_index = graph_index
        if self.graph_index is None:
            import os
            if os.getenv("ASSEST_DEV_MODE") == "sandbox" or os.getenv("QDRANT_MODE") == "memory":
                self.graph_index = NullGraphIndex()
            else:
                try:
                    self.graph_index = GraphIndex()
                except Exception as e:
                    logger.warning("GraphStore init failed (non-fatal): %s", e)
                    self.graph_index = None
        self.entity_resolver_factory = entity_resolver_factory

    async def process(
        self,
        raw_doc: Any,
        workspace_id: str,
        connector_id: Optional[str] = None,
    ) -> DocumentIngestionResult:
        try:
            resolver = self.entity_resolver_factory()

            logger.info("Processing: %s (%s)", raw_doc.title, raw_doc.source_type)

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

            version_plan = await self.document_store.prepare_version(raw_doc, workspace_id)
            if version_plan.should_skip:
                return DocumentIngestionResult(status="skipped")

            raw_content = normalized.raw_content or getattr(
                raw_doc,
                "raw_content",
                getattr(raw_doc, "content", ""),
            )
            content_format = getattr(raw_doc, "content_format", "text")
            file_name = getattr(raw_doc, "title", "document")
            if hasattr(raw_doc, "source_url") and "." in raw_doc.source_url:
                file_name = raw_doc.source_url.split("/")[-1]

            if isinstance(raw_content, bytes) or (
                isinstance(raw_content, str)
                and len(raw_content) < 1000
                and any(raw_content.lower().endswith(ext) for ext in [".pdf", ".png", ".jpg", ".mp3"])
            ):
                content_bytes = raw_content if isinstance(raw_content, bytes) else raw_content.encode()
                elements = await self.parser.parse_bytes(content_bytes, file_name)
            elif content_format == "html":
                elements = self.parser._parse_html_string(raw_content)
            else:
                elements = [{"type": "text", "content": raw_content, "metadata": {}}]

            if not elements:
                elements = [{"type": "text", "content": str(raw_content), "metadata": {}}]

            scrubbed_elements = []
            for el in elements:
                scrubbed_text, _ = self.scrubber.scrub(el["content"])
                el["content"] = scrubbed_text
                scrubbed_elements.append(el)

            full_text = "\n\n".join([el["content"] for el in scrubbed_elements])
            tier = getattr(raw_doc, "tier", 2)
            doc_title = normalized.title or raw_doc.title
            doc_type = await self.classifier.classify(full_text, doc_title)

            enriched_metadata = {"entities": [], "topics": [], "keywords": [], "summary": "", "events": []}
            if self.extractor:
                try:
                    logger.info("Enriching metadata for: %s using extractor=%s", doc_title, type(self.extractor))
                    raw_metadata = await self.extractor.extract_semantic_metadata(full_text)
                    enriched_metadata.update(raw_metadata)
                    enriched_metadata["summary"], _ = self.scrubber.scrub(enriched_metadata.get("summary", ""))
                except Exception as e:
                    logger.warning("Semantic enrichment failed: %s", e)

            extracted_entities = enriched_metadata.get("entities", [])
            resolved_entities = []
            if extracted_entities:
                async with async_session() as session:
                    resolved_entities = await resolver.resolve_and_link(
                        session=session,
                        workspace_id=workspace_id,
                        document_id=str(uuid.uuid4()),
                        entities=extracted_entities,
                    )

            chunks_data = self.chunker.chunk_elements(scrubbed_elements, doc_type="auto")
            
            # Hierarchical Parent-Child & Contextual Retrieval logic
            contextualizer = ChunkContextualizer()
            hierarchical_chunks = []
            flat_child_chunks = []
            doc_content = full_text
            doc_title = normalized.title or raw_doc.title
            
            for c in chunks_data:
                parent_text = c.get("raw_content", c.get("content", ""))
                children_texts = c.get("children", [])
                heading_path = c.get("heading_path", [])
                chunk_type = c.get("type", "text")
                structural_metadata = c.get("structural_metadata", {})
                
                hierarchical_children = []
                for child_text in children_texts:
                    if contextualizer.enabled:
                        context = await contextualizer.contextualize(
                            doc_title=doc_title,
                            doc_content=doc_content,
                            chunk_content=child_text
                        )
                        if context:
                            contextualized_text = f"<context>\n{context}\n</context>\n{child_text}"
                        else:
                            contextualized_text = child_text
                    else:
                        contextualized_text = child_text
                    
                    hierarchical_children.append({
                        "raw_content": child_text,
                        "contextualized_content": contextualized_text
                    })
                    flat_child_chunks.append(contextualized_text)
                    
                hierarchical_chunks.append({
                    "parent_content": parent_text,
                    "heading_path": heading_path,
                    "chunk_type": chunk_type,
                    "structural_metadata": structural_metadata,
                    "children": hierarchical_children
                })

            if not flat_child_chunks:
                flat_child_chunks = [c["content"] for c in chunks_data]
            chunks = flat_child_chunks

            # Prepare child payloads
            child_payloads = [
                {
                    "title": raw_doc.title,
                    "source_url": raw_doc.source_url,
                    "source_type": raw_doc.source_type,
                    "content_tier": tier,
                    "extracted_entities": [
                        e.get("name") if isinstance(e, dict) else getattr(e, "name", str(e))
                        for e in (resolved_entities or extracted_entities)
                    ],
                    "summary": enriched_metadata.get("summary", ""),
                    "version": version_plan.current_version,
                    "is_active": True,
                }
                for _ in range(len(chunks))
            ]

            # Persist document and chunks via helper (centralised behaviour)
            doc_record = await self.persist_document_and_chunks(
                raw_doc, workspace_id, connector_id, doc_type, getattr(raw_doc, "content_hash", str(hash(raw_content))), chunks, child_payloads,
                version_plan,
                tags=enriched_metadata.get("keywords", []),
                hierarchical_chunks=hierarchical_chunks,
            )

            # Index embeddings (blocking embedder used deliberately via embed_multi)
            self.embed_and_index(workspace_id, raw_doc, chunks, enriched_metadata, version=version_plan.current_version, payloads=child_payloads)

            # Persist graph & events via helper
            extracted_events = enriched_metadata.get("events", [])
            await self.persist_graph_and_events(workspace_id, doc_record, raw_doc, resolved_entities, extracted_events)

            logger.info("Finished Ingestion: %s", doc_title)
            return DocumentIngestionResult(
                status="processed",
                document_id=doc_record.id,
                version=version_plan.current_version,
                chunk_count=len(chunks),
            )

        except DocumentIngestionError:
            raise
        except Exception as e:
            title = getattr(raw_doc, "title", "unknown")
            logger.error("Error processing document %s: %s", title, e)
            raise DocumentIngestionError(
                message=str(e),
                failure_snapshot={
                    "title": title,
                    "source_id": getattr(raw_doc, "source_id", "unknown"),
                    "source_url": getattr(raw_doc, "source_url", "unknown"),
                    "source_type": getattr(raw_doc, "source_type", "unknown"),
                },
            ) from e

    # ── Stage-based processing helpers (allow external pipeline orchestration) ──
    async def prepare_and_version(self, raw_doc: Any, workspace_id: str):
        """Normalize and prepare version plan."""
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
        version_plan = await self.document_store.prepare_version(raw_doc, workspace_id)
        return normalized, version_plan

    async def parse_and_scrub(self, raw_doc: Any, normalized, workspace_id: str):
        raw_content = normalized.raw_content or getattr(raw_doc, "raw_content", getattr(raw_doc, "content", ""))
        content_format = getattr(raw_doc, "content_format", "text")
        file_name = getattr(raw_doc, "title", "document")
        if hasattr(raw_doc, "source_url") and "." in raw_doc.source_url:
            file_name = raw_doc.source_url.split("/")[-1]

        if isinstance(raw_content, bytes) or (
            isinstance(raw_content, str)
            and len(raw_content) < 1000
            and any(raw_content.lower().endswith(ext) for ext in [".pdf", ".png", ".jpg", ".mp3"])
        ):
            content_bytes = raw_content if isinstance(raw_content, bytes) else raw_content.encode()
            elements = await self.parser.parse_bytes(content_bytes, file_name)
        elif content_format == "html":
            elements = self.parser._parse_html_string(raw_content)
        else:
            elements = [{"type": "text", "content": raw_content, "metadata": {}}]

        if not elements:
            elements = [{"type": "text", "content": str(raw_content), "metadata": {}}]

        scrubbed_elements = []
        for el in elements:
            scrubbed_text, _ = self.scrubber.scrub(el["content"])
            el["content"] = scrubbed_text
            scrubbed_elements.append(el)

        return scrubbed_elements

    async def enrich_and_classify(self, raw_doc: Any, scrubbed_elements, workspace_id: str):
        full_text = "\n\n".join([el["content"] for el in scrubbed_elements])
        tier = getattr(raw_doc, "tier", 2)
        doc_title = getattr(raw_doc, "title", "")
        doc_type = await self.classifier.classify(full_text, doc_title)

        enriched_metadata = {"entities": [], "topics": [], "keywords": [], "summary": "", "events": []}
        if self.extractor:
            try:
                raw_metadata = await self.extractor.extract_semantic_metadata(full_text)
                enriched_metadata.update(raw_metadata)
                enriched_metadata["summary"], _ = self.scrubber.scrub(enriched_metadata.get("summary", ""))
            except Exception as e:
                logger.warning("Semantic enrichment failed: %s", e)
        return doc_type, enriched_metadata, tier

    async def resolve_entities(self, extracted_entities, workspace_id: str):
        if not extracted_entities:
            return []
        resolver = self.entity_resolver_factory()
        async with async_session() as session:
            resolved = await resolver.resolve_and_link(
                session=session,
                workspace_id=workspace_id,
                document_id=str(uuid.uuid4()),
                entities=extracted_entities,
            )
        return resolved

    async def chunk_and_prepare_hierarchical(self, scrubbed_elements, doc_type: str, raw_doc: Any, enriched_metadata, version, doc_title: str, doc_content: str):
        chunks_data = self.chunker.chunk_elements(scrubbed_elements, doc_type="auto")
        
        contextualizer = ChunkContextualizer()
        hierarchical_chunks = []
        flat_child_chunks = []
        
        for c in chunks_data:
            parent_text = c.get("raw_content", c.get("content", ""))
            children_texts = c.get("children", [])
            heading_path = c.get("heading_path", [])
            chunk_type = c.get("type", "text")
            structural_metadata = c.get("structural_metadata", {})
            
            hierarchical_children = []
            for child_text in children_texts:
                if contextualizer.enabled:
                    context = await contextualizer.contextualize(
                        doc_title=doc_title,
                        doc_content=doc_content,
                        chunk_content=child_text
                    )
                    if context:
                        contextualized_text = f"<context>\n{context}\n</context>\n{child_text}"
                    else:
                        contextualized_text = child_text
                else:
                    contextualized_text = child_text
                
                hierarchical_children.append({
                    "raw_content": child_text,
                    "contextualized_content": contextualized_text
                })
                flat_child_chunks.append(contextualized_text)
                
            hierarchical_chunks.append({
                "parent_content": parent_text,
                "heading_path": heading_path,
                "chunk_type": chunk_type,
                "structural_metadata": structural_metadata,
                "children": hierarchical_children
            })

        if not flat_child_chunks:
            flat_child_chunks = [c["content"] for c in chunks_data]
            
        chunks = flat_child_chunks
        
        payloads = [
            {
                "title": raw_doc.title,
                "source_url": raw_doc.source_url,
                "source_type": raw_doc.source_type,
                "content_tier": getattr(raw_doc, "tier", 2),
                "extracted_entities": [
                    e.get("name") if isinstance(e, dict) else getattr(e, "name", str(e))
                    for e in (enriched_metadata.get("entities", []) or [])
                ],
                "summary": enriched_metadata.get("summary", ""),
                "version": version,
                "is_active": True,
            }
            for _ in chunks
        ]
        return chunks, payloads, hierarchical_chunks

    async def persist_document_and_chunks(self, raw_doc, workspace_id, connector_id, doc_type, content_hash, chunks, payloads, version_plan, tags: Optional[list] = None, hierarchical_chunks: Optional[list] = None):
        if tags is None:
            tags = []
        if hasattr(self.document_store, "persist_document_bundle"):
            return await self.document_store.persist_document_bundle(
                raw_doc=raw_doc,
                workspace_id=workspace_id,
                connector_id=connector_id,
                doc_type=doc_type,
                content_hash=content_hash,
                chunk_count=len(chunks),
                tier=getattr(raw_doc, "tier", 2),
                tags=tags,
                version=version_plan.current_version,
                previous_document_id=version_plan.previous_document_id,
                chunks=chunks,
                payloads=payloads,
                hierarchical_chunks=hierarchical_chunks,
            )

        doc_record = await self.document_store.persist_document(
            raw_doc=raw_doc,
            workspace_id=workspace_id,
            connector_id=connector_id,
            doc_type=doc_type,
            content_hash=content_hash,
            chunk_count=len(chunks),
            tier=getattr(raw_doc, "tier", 2),
            tags=tags,
            version=version_plan.current_version,
            previous_document_id=version_plan.previous_document_id,
        )
        await self.document_store.persist_chunks(
            document_id=doc_record.id,
            workspace_id=workspace_id,
            chunks=chunks,
            payloads=payloads,
            version=version_plan.current_version,
            hierarchical_chunks=hierarchical_chunks,
        )
        return doc_record

    def embed_and_index(self, workspace_id: str, raw_doc: Any, chunks, enriched_metadata, version: int = 1, payloads: Optional[list] = None):
        multi_embeddings = self.embedder.embed_multi(
            chunks=chunks,
            title=raw_doc.title,
            summary=enriched_metadata.get("summary", ""),
        )
        if payloads is None:
            payloads = [{
                "title": raw_doc.title,
                "source_url": raw_doc.source_url,
                "source_type": raw_doc.source_type,
                "content_tier": getattr(raw_doc, "tier", 2),
                "extracted_entities": [],
                "summary": enriched_metadata.get("summary", ""),
                "version": version,
                "is_active": True,
            } for _ in range(len(chunks))]
        self.vector_index.upsert_batch(workspace_id, multi_embeddings, payloads)

    async def persist_graph_and_events(self, workspace_id: str, doc_record, raw_doc: Any, resolved_entities, extracted_events):
        if self.graph_index:
            try:
                self.graph_index.add_document_artifacts(
                    workspace_id=workspace_id,
                    document_id=doc_record.id,
                    title=raw_doc.title,
                    source_url=raw_doc.source_url,
                    resolved_entities=resolved_entities,
                    events=extracted_events,
                )
                await self.document_store.persist_events(workspace_id, doc_record.id, extracted_events)
            except Exception as ge:
                logger.warning("Graph storage failed: %s", ge)

    async def process_stagewise(self, raw_doc: Any, workspace_id: str, connector_id: Optional[str] = None) -> DocumentIngestionResult:
        try:
            normalized, version_plan = await self.prepare_and_version(raw_doc, workspace_id)
            if version_plan.should_skip:
                return DocumentIngestionResult(status="skipped")

            scrubbed_elements = await self.parse_and_scrub(raw_doc, normalized, workspace_id)
            doc_type, enriched_metadata, tier = await self.enrich_and_classify(raw_doc, scrubbed_elements, workspace_id)
            extracted_entities = enriched_metadata.get("entities", [])
            resolved_entities = await self.resolve_entities(extracted_entities, workspace_id)
            chunks, payloads, hierarchical_chunks = await self.chunk_and_prepare_hierarchical(
                scrubbed_elements, doc_type, raw_doc, enriched_metadata, version_plan.current_version,
                doc_title=normalized.title or raw_doc.title,
                doc_content="\n\n".join([el["content"] for el in scrubbed_elements])
            )

            # Persist document and chunks
            doc_record = await self.persist_document_and_chunks(
                raw_doc, workspace_id, connector_id, doc_type, getattr(raw_doc, "content_hash", str(hash(normalized.raw_content))), chunks, payloads, version_plan, tags=enriched_metadata.get("keywords", []), hierarchical_chunks=hierarchical_chunks
            )

            # Index embeddings (blocking embedder used deliberately via embed_multi)
            self.embed_and_index(workspace_id, raw_doc, chunks, enriched_metadata, version=version_plan.current_version, payloads=payloads)

            # Persist graph & events
            extracted_events = enriched_metadata.get("events", [])
            await self.persist_graph_and_events(workspace_id, doc_record, raw_doc, resolved_entities, extracted_events)

            return DocumentIngestionResult(
                status="processed",
                document_id=doc_record.id,
                version=version_plan.current_version,
                chunk_count=len(chunks),
            )
        except DocumentIngestionError:
            raise
        except Exception as e:
            title = getattr(raw_doc, "title", "unknown")
            logger.error("Stagewise error processing document %s: %s", title, e)
            raise DocumentIngestionError(
                message=str(e),
                failure_snapshot={
                    "title": title,
                    "source_id": getattr(raw_doc, "source_id", "unknown"),
                    "source_url": getattr(raw_doc, "source_url", "unknown"),
                    "source_type": getattr(raw_doc, "source_type", "unknown"),
                },
            ) from e

    def close(self) -> None:
        if self.graph_index:
            self.graph_index.close()
