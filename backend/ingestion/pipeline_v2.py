import logging
import uuid
from datetime import datetime
from typing import Protocol, Any, Optional
from sqlalchemy import select, update

from backend.core.database import async_session
from backend.models.document import Document
from backend.models.chunk import Chunk as DBChunk
from backend.models.knowledge_event import KnowledgeEvent
from backend.core.vector_store import VectorStore
from backend.graph.graph_store import GraphStore
from backend.graph.entity_resolver import EntityResolver
from backend.ingestion.document_run import IngestionPackage, IngestionState
from backend.core.config import get_settings
from backend.ingestion.contextualizer import ChunkContextualizer
from backend.ingestion.document_store import VersionPlan

logger = logging.getLogger(__name__)
settings = get_settings()

class Transformer(Protocol):
    async def transform(self, package: IngestionPackage) -> None:
        ...

class NormalizerTransformer:
    def __init__(self, normalizer: Any):
        self.normalizer = normalizer

    async def transform(self, package: IngestionPackage) -> None:
        raw_data = {
            "source_id": getattr(package.raw_doc, "source_id", "unknown"),
            "title": getattr(package.raw_doc, "title", "Untitled"),
            "content": getattr(package.raw_doc, "raw_content", getattr(package.raw_doc, "content", "")),
            "source_url": getattr(package.raw_doc, "source_url", ""),
            "metadata": getattr(package.raw_doc, "metadata", {}),
            "permissions": getattr(package.raw_doc, "permissions", []),
        }
        
        # Handle dict raw_doc for tests
        if isinstance(package.raw_doc, dict):
            raw_data.update(package.raw_doc)

        normalized = self.normalizer.normalize_generic(
            raw_data,
            workspace_id=package.workspace_id,
        )
        
        package.set_normalized(
            title=normalized.title,
            content=normalized.raw_content,
            metadata={} # Additional metadata can be added here
        )

class ParserTransformer:
    def __init__(self, parser: Any):
        self.parser = parser

    async def transform(self, package: IngestionPackage) -> None:
        raw_content = package.content or getattr(package.raw_doc, "raw_content", getattr(package.raw_doc, "content", ""))
        content_format = getattr(package.raw_doc, "content_format", "text")
        file_name = package.title or "document"
        
        if hasattr(package.raw_doc, "source_url") and "." in package.raw_doc.source_url:
            file_name = package.raw_doc.source_url.split("/")[-1]
        
        if isinstance(raw_content, bytes) or (
            isinstance(raw_content, str)
            and len(raw_content) < 1000
            and any(raw_content.lower().endswith(ext) for ext in [".pdf", ".png", ".jpg", ".mp3"])
        ):
            content_bytes = raw_content if isinstance(raw_content, bytes) else str(raw_content).encode()
            elements = await self.parser.parse_bytes(content_bytes, file_name)
        elif content_format == "html":
            elements = self.parser._parse_html_string(raw_content)
        else:
            elements = [{"type": "text", "content": str(raw_content), "metadata": {}}]

        if not elements:
            elements = [{"type": "text", "content": str(raw_content), "metadata": {}}]

        package.set_elements(elements)

class ScrubberTransformer:
    def __init__(self, scrubber: Any):
        self.scrubber = scrubber

    async def transform(self, package: IngestionPackage) -> None:
        scrubbed_elements = []
        for el in package.elements:
            scrubbed_text, _ = self.scrubber.scrub(el["content"])
            new_el = el.copy()
            new_el["content"] = scrubbed_text
            scrubbed_elements.append(new_el)
        package.set_scrubbed(scrubbed_elements)

class ClassifierTransformer:
    def __init__(self, classifier: Any):
        self.classifier = classifier

    async def transform(self, package: IngestionPackage) -> None:
        # Coerce element content to strings to avoid MagicMock or non-str values
        full_text = "\n\n".join([str(el.get("content", "")) for el in package.elements])
        doc_title = package.title or ""
        doc_type = await self.classifier.classify(full_text, doc_title)
        package.set_classified(doc_type)

class ChunkerTransformer:
    def __init__(self, chunker: Any):
        self.chunker = chunker
        self.contextualizer = ChunkContextualizer()

    async def transform(self, package: IngestionPackage) -> None:
        doc_type = package.metadata.get("document_type", "auto")
        # Ensure element contents are strings to avoid test-injected MagicMock or lists
        safe_elements = [{**el, "content": str(el.get("content", ""))} for el in package.elements]
        chunks_data = self.chunker.chunk_elements(safe_elements, doc_type=doc_type)
        
        doc_content = package.content or "\n\n".join([el["content"] for el in safe_elements])
        doc_title = package.title or "Untitled"

        hierarchical_chunks = []
        flat_child_chunks = []
        
        for c in chunks_data:
            parent_text = c["raw_content"]
            children_texts = c.get("children", [])
            heading_path = c.get("heading_path", [])
            chunk_type = c.get("type", "text")
            structural_metadata = c.get("structural_metadata", {})
            
            hierarchical_children = []
            for child_text in children_texts:
                if self.contextualizer.enabled:
                    context = await self.contextualizer.contextualize(
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
            
        package.metadata["hierarchical_chunks"] = hierarchical_chunks
        
        if not flat_child_chunks:
            flat_child_chunks = [c["content"] for c in chunks_data]
            
        package.set_chunks(flat_child_chunks)

class EmbedderTransformer:
    def __init__(self, embedder: Any):
        self.embedder = embedder

    async def transform(self, package: IngestionPackage) -> None:
        summary = package.metadata.get("summary", "")
        embeddings = await self.embedder.aembed_multi(
            chunks=package.chunks,
            title=package.title or "Untitled",
            summary=summary
        )
        package.set_embeddings(embeddings)

class ExtractorTransformer:
    def __init__(self, extractor: Any, scrubber: Optional[Any] = None):
        self.extractor = extractor
        self.scrubber = scrubber

    async def transform(self, package: IngestionPackage) -> None:
        # Coerce element content to strings to avoid MagicMock or non-str values
        full_text = "\n\n".join([str(el.get("content", "")) for el in package.elements])
        try:
            raw_metadata = await self.extractor.extract_semantic_metadata(full_text)
            if self.scrubber and raw_metadata.get("summary"):
                scrubbed_summary, _ = self.scrubber.scrub(raw_metadata["summary"])
                raw_metadata["summary"] = scrubbed_summary
            package.set_enriched(raw_metadata)
        except Exception:
            pass

class KnowledgeStore:
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        graph_store: Optional[GraphStore] = None,
        entity_resolver: Optional[EntityResolver] = None,
        document_store: Optional[Any] = None,
        index_adapter: Optional[Any] = None,
    ):
        """KnowledgeStore optionally delegates persistence to a DocumentStore and indexing to an IndexAdapter.

        Backwards-compatible: if `document_store` or `index_adapter` are not provided,
        the store falls back to the previous internal persistence behaviour.
        """
        self.vector_store = vector_store or VectorStore()
        self.graph_store = graph_store
        self.entity_resolver = entity_resolver
        self.document_store = document_store
        self.index_adapter = index_adapter

    async def prepare_version(self, package: IngestionPackage) -> VersionPlan:
        # Delegate to document_store when available for consistent versioning
        if self.document_store:
            return await self.document_store.prepare_version(package.raw_doc, package.workspace_id)

        async with async_session() as session:
            source_url = getattr(package.raw_doc, "source_url", "")
            if not source_url:
                return VersionPlan()

            stmt = select(Document).where(
                Document.source_url == source_url,
                Document.workspace_id == package.workspace_id,
                Document.is_active == True,
            )
            res = await session.execute(stmt)
            existing_doc = res.scalars().first()

            if not existing_doc:
                return VersionPlan()

            content_hash = getattr(package.raw_doc, "content_hash", str(hash(package.content or "")))
            if existing_doc.content_hash == content_hash:
                logger.info("Deduplication hit: skipping %s", package.title)
                return VersionPlan(should_skip=True)

            logger.info("Versioning: Archiving v%s of %s", existing_doc.version, package.title)
            existing_doc.is_active = False
            await session.execute(
                update(DBChunk)
                .where(DBChunk.document_id == existing_doc.id)
                .values(is_active=False)
            )
            await session.commit()
            return VersionPlan(
                current_version=existing_doc.version + 1,
                previous_document_id=existing_doc.id,
            )

    async def persist(self, package: IngestionPackage) -> None:
        version_plan = await self.prepare_version(package)
        if version_plan.should_skip:
            package.state = IngestionState.PERSISTED
            return

        # If a DocumentStore is available, delegate SQL persistence to it for consistency
        if self.document_store:
            # Prepare payloads for chunks
            payloads = [
                {
                    "title": package.title or getattr(package.raw_doc, "title", "Untitled"),
                    "source_url": getattr(package.raw_doc, "source_url", ""),
                    "source_type": getattr(package.raw_doc, "source_type", "unknown"),
                    "content_tier": getattr(package.raw_doc, "tier", 2),
                    "extracted_entities": [e.get("name") if isinstance(e, dict) else e for e in package.metadata.get("entities", [])],
                    "summary": package.metadata.get("summary", ""),
                    "version": version_plan.current_version,
                    "is_active": True,
                }
                for _ in package.chunks
            ]

            if hasattr(self.document_store, "persist_document_bundle"):
                doc_record = await self.document_store.persist_document_bundle(
                    raw_doc=package.raw_doc,
                    workspace_id=package.workspace_id,
                    connector_id=package.connector_id,
                    doc_type=package.metadata.get("document_type", "auto"),
                    content_hash=getattr(package.raw_doc, "content_hash", str(hash(package.content or ""))),
                    chunk_count=len(package.chunks),
                    tier=getattr(package.raw_doc, "tier", 2),
                    tags=package.metadata.get("keywords", []),
                    version=version_plan.current_version,
                    previous_document_id=version_plan.previous_document_id,
                    chunks=package.chunks,
                    payloads=payloads,
                    hierarchical_chunks=package.metadata.get("hierarchical_chunks"),
                )
                package.doc_record = doc_record
            else:
                # Persist document record
                doc_record = await self.document_store.persist_document(
                    raw_doc=package.raw_doc,
                    workspace_id=package.workspace_id,
                    connector_id=package.connector_id,
                    doc_type=package.metadata.get("document_type", "auto"),
                    content_hash=getattr(package.raw_doc, "content_hash", str(hash(package.content or ""))),
                    chunk_count=len(package.chunks),
                    tier=getattr(package.raw_doc, "tier", 2),
                    tags=package.metadata.get("keywords", []),
                    version=version_plan.current_version,
                    previous_document_id=version_plan.previous_document_id,
                )
                package.doc_record = doc_record

                # Persist chunks
                if package.chunks:
                    await self.document_store.persist_chunks(
                        document_id=doc_record.id,
                        workspace_id=package.workspace_id,
                        chunks=package.chunks,
                        payloads=payloads,
                        version=version_plan.current_version,
                        hierarchical_chunks=package.metadata.get("hierarchical_chunks"),
                    )

            # Update dynamic BM25 sparse indexer in-memory
            try:
                from backend.query.sparse_indexer import get_sparse_indexer
                sparse_indexer = get_sparse_indexer()
                hierarchical_chunks = package.metadata.get("hierarchical_chunks")
                if hierarchical_chunks:
                    child_idx = 0
                    for parent_chunk_data in hierarchical_chunks:
                        for child_data in parent_chunk_data["children"]:
                            child_text = child_data["contextualized_content"]
                            child_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_record.id}:child:{child_idx}"))
                            sparse_indexer.add_document(child_id, child_text)
                            child_idx += 1
                else:
                    for idx, chunk_text in enumerate(package.chunks):
                        c_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_record.id}:{idx}"))
                        sparse_indexer.add_document(c_id, chunk_text)
            except Exception as se:
                logger.warning(f"Failed to update BM25 index: {se}")

            # Index embeddings via index_adapter if available; otherwise use vector_store
            if package.embeddings:
                if self.index_adapter:
                    await self.index_adapter.upsert_vectors(package.workspace_id, package.embeddings, payloads)
                else:
                    try:
                        self.vector_store.upsert_batch(package.workspace_id, package.embeddings, payloads)
                    except Exception as ve:
                        logger.warning("Vector storage failed: %s", ve)

            # Persist graph artifacts via index_adapter or graph_store
            resolved_entities = package.metadata.get("entities", [])
            extracted_events = package.metadata.get("events", [])
            if self.index_adapter:
                await self.index_adapter.add_graph_artifacts(package.workspace_id, doc_record.id, resolved_entities, extracted_events)
            elif self.graph_store:
                try:
                    self.graph_store.add_document_node(
                        workspace_id=package.workspace_id,
                        document_id=doc_record.id,
                        title=doc_record.title,
                        source_url=doc_record.source_url,
                    )
                    if resolved_entities:
                        self.graph_store.add_entities_and_relationships(doc_record.id, resolved_entities)
                    for event_data in extracted_events:
                        self.graph_store.add_event_node(doc_record.id, event_data)
                except Exception as ge:
                    logger.warning("Graph storage failed: %s", ge)

        else:
            # Fallback to previous inline persistence behaviour
            async with async_session() as session:
                # 1. Prepare Document Record
                doc_id = str(uuid.uuid4())
                doc_record = Document(
                    id=doc_id,
                    workspace_id=package.workspace_id,
                    connector_id=package.connector_id,
                    source_url=getattr(package.raw_doc, "source_url", ""),
                    title=package.title or getattr(package.raw_doc, "title", "Untitled"),
                    document_type=package.metadata.get("document_type", "auto"),
                    content_hash=getattr(package.raw_doc, "content_hash", str(hash(package.content or ""))),
                    chunk_count=len(package.chunks),
                    tier=getattr(package.raw_doc, "tier", 2),
                    tags=package.metadata.get("keywords", []),
                    version=version_plan.current_version,
                    previous_version_id=version_plan.previous_document_id,
                    is_active=True,
                )
                session.add(doc_record)
                package.doc_record = doc_record

                # 2. Prepare Chunks
                payloads = []
                hierarchical_chunks = package.metadata.get("hierarchical_chunks")
                if hierarchical_chunks:
                    child_idx = 0
                    for parent_idx, parent_chunk_data in enumerate(hierarchical_chunks):
                        parent_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:parent:{parent_idx}"))
                        parent_text = parent_chunk_data["parent_content"]
                        
                        parent_db_chunk = DBChunk(
                            id=parent_id,
                            document_id=doc_id,
                            workspace_id=package.workspace_id,
                            content=parent_text,
                            parent_id=None,
                            heading_path=parent_chunk_data.get("heading_path", []),
                            chunk_type=parent_chunk_data.get("chunk_type", "text"),
                            structural_metadata=parent_chunk_data.get("structural_metadata", {}),
                            chunk_index=parent_idx,
                            tier=doc_record.tier,
                            source_type=getattr(package.raw_doc, "source_type", "unknown"),
                            source_url=doc_record.source_url,
                            document_title=doc_record.title,
                            version=version_plan.current_version,
                            is_active=True,
                        )
                        session.add(parent_db_chunk)
                        
                        for c_j, child_data in enumerate(parent_chunk_data["children"]):
                            child_text = child_data["contextualized_content"]
                            child_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:child:{child_idx}"))
                            
                            payload = {
                                "title": doc_record.title,
                                "source_url": doc_record.source_url,
                                "source_type": getattr(package.raw_doc, "source_type", "unknown"),
                                "content_tier": doc_record.tier,
                                "extracted_entities": [e.get("name") if isinstance(e, dict) else e for e in package.metadata.get("entities", [])],
                                "summary": package.metadata.get("summary", ""),
                                "version": version_plan.current_version,
                                "is_active": True,
                                "parent_id": parent_id,
                            }
                            payloads.append(payload)
                            
                            child_db_chunk = DBChunk(
                                id=child_id,
                                document_id=doc_id,
                                workspace_id=package.workspace_id,
                                content=child_text,
                                parent_id=parent_id,
                                heading_path=parent_chunk_data.get("heading_path", []),
                                chunk_type="text",
                                chunk_index=child_idx,
                                tier=payload.get("content_tier", 2),
                                source_type=payload.get("source_type"),
                                source_url=payload.get("source_url"),
                                document_title=payload.get("title"),
                                version=version_plan.current_version,
                                is_active=True,
                            )
                            session.add(child_db_chunk)
                            child_idx += 1
                else:
                    for idx, chunk_text in enumerate(package.chunks):
                        c_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{idx}"))
                        payload = {
                            "title": doc_record.title,
                            "source_url": doc_record.source_url,
                            "source_type": getattr(package.raw_doc, "source_type", "unknown"),
                            "content_tier": doc_record.tier,
                            "extracted_entities": [e.get("name") if isinstance(e, dict) else e for e in package.metadata.get("entities", [])],
                            "summary": package.metadata.get("summary", ""),
                            "version": version_plan.current_version,
                            "is_active": True,
                        }
                        payloads.append(payload)

                        new_chunk = DBChunk(
                            id=c_id,
                            document_id=doc_id,
                            workspace_id=package.workspace_id,
                            content=chunk_text,
                            chunk_index=idx,
                            tier=payload.get("content_tier", 2),
                            source_type=payload.get("source_type"),
                            source_url=payload.get("source_url"),
                            document_title=payload.get("title"),
                            version=version_plan.current_version,
                            is_active=True,
                        )
                        session.add(new_chunk)

                # 3. Resolve Entities (needs a session)
                resolved_entities = []
                extracted_entities = package.metadata.get("entities", [])
                if self.entity_resolver and extracted_entities:
                    resolved_entities = await self.entity_resolver.resolve_and_link(
                        session=session,
                        workspace_id=package.workspace_id,
                        document_id=doc_id,
                        entities=extracted_entities,
                    )
                    
                # 4. Prepare Events
                extracted_events = package.metadata.get("events", [])
                if extracted_events:
                    for event_data in extracted_events:
                        new_event = KnowledgeEvent(
                            workspace_id=package.workspace_id,
                            event_type=event_data.get("type", "milestone"),
                            title=event_data.get("title", "Unknown Event"),
                            description=event_data.get("description"),
                            timestamp=datetime.utcnow(),
                            source_document_id=doc_id,
                            metadata_json=event_data,
                        )
                        session.add(new_event)

                # Atomic SQL Commit
                await session.commit()

                # Update dynamic BM25 sparse indexer in-memory
                try:
                    from backend.query.sparse_indexer import get_sparse_indexer
                    sparse_indexer = get_sparse_indexer()
                    hierarchical_chunks = package.metadata.get("hierarchical_chunks")
                    if hierarchical_chunks:
                        child_idx = 0
                        for parent_chunk_data in hierarchical_chunks:
                            for child_data in parent_chunk_data["children"]:
                                child_text = child_data["contextualized_content"]
                                child_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:child:{child_idx}"))
                                sparse_indexer.add_document(child_id, child_text)
                                child_idx += 1
                    else:
                        for idx, chunk_text in enumerate(package.chunks):
                            c_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{idx}"))
                            sparse_indexer.add_document(c_id, chunk_text)
                except Exception as se:
                    logger.warning(f"Failed to update BM25 index: {se}")

                # 5. Vector Store Persistence (external)
                if package.embeddings:
                    try:
                        self.vector_store.upsert_batch(package.workspace_id, package.embeddings, payloads)
                    except Exception as ve:
                        logger.warning("Vector storage failed: %s", ve)

                # 6. Graph Store Persistence (external)
                if self.graph_store:
                    try:
                        self.graph_store.add_document_node(
                            workspace_id=package.workspace_id,
                            document_id=doc_id,
                            title=doc_record.title,
                            source_url=doc_record.source_url
                        )
                        if resolved_entities:
                            self.graph_store.add_entities_and_relationships(doc_id, resolved_entities)
                        for event_data in extracted_events:
                            self.graph_store.add_event_node(doc_id, event_data)
                    except Exception as ge:
                        logger.warning("Graph storage failed: %s", ge)

        package.state = IngestionState.PERSISTED

class PipelineTemplate:
    def __init__(self, transformers: list[Transformer]):
        self.transformers = transformers

class DefaultTemplate(PipelineTemplate):
    def __init__(
        self,
        normalizer: Any,
        parser: Any,
        scrubber: Any,
        classifier: Any,
        chunker: Any,
        embedder: Any,
        extractor: Optional[Any] = None,
    ):
        transformers = [
            NormalizerTransformer(normalizer),
            ParserTransformer(parser),
            ScrubberTransformer(scrubber),
            ClassifierTransformer(classifier),
            ExtractorTransformer(extractor, scrubber) if extractor else None,
            ChunkerTransformer(chunker),
            EmbedderTransformer(embedder),
        ]
        super().__init__([t for t in transformers if t is not None])

class PDFTemplate(PipelineTemplate):
    def __init__(
        self,
        normalizer: Any,
        parser: Any,
        scrubber: Any,
        classifier: Any,
        chunker: Any,
        embedder: Any,
        extractor: Optional[Any] = None,
    ):
        # PDFs might use the same transformers for now, but the template allows for specialization
        transformers = [
            NormalizerTransformer(normalizer),
            ParserTransformer(parser),
            ScrubberTransformer(scrubber),
            ClassifierTransformer(classifier),
            ExtractorTransformer(extractor, scrubber) if extractor else None,
            ChunkerTransformer(chunker),
            EmbedderTransformer(embedder),
        ]
        super().__init__([t for t in transformers if t is not None])

class IngestionRunner:
    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        templates: Optional[dict[str, PipelineTemplate]] = None,
        default_template: Optional[PipelineTemplate] = None,
    ):
        self.knowledge_store = knowledge_store
        self.templates = templates or {}
        self.default_template = default_template

    def select_template(self, package: IngestionPackage) -> Optional[PipelineTemplate]:
        # 1. Check explicit document_type in metadata
        doc_type = package.metadata.get("document_type")
        if doc_type and doc_type.lower() in self.templates:
            return self.templates[doc_type.lower()]

        # 2. Check source_type on raw_doc
        source_type = getattr(package.raw_doc, "source_type", None)
        if source_type and source_type.lower() in self.templates:
            return self.templates[source_type.lower()]

        # 3. Check file extension in source_url
        source_url = getattr(package.raw_doc, "source_url", "")
        if source_url.lower().endswith(".pdf") and "pdf" in self.templates:
            return self.templates["pdf"]

        return self.default_template

    async def process(self, raw_doc: Any, workspace_id: str, connector_id: Optional[str] = None) -> IngestionPackage:
        package = IngestionPackage(raw_doc=raw_doc, workspace_id=workspace_id, connector_id=connector_id)
        await self.run(package)
        return package

    async def run(self, package: IngestionPackage) -> None:
        template = self.select_template(package)
        if not template:
            logger.error("No template found for package: %s", package.title)
            package.state = IngestionState.FAILED
            return

        try:
            for transformer in template.transformers:
                await transformer.transform(package)
            
            await self.knowledge_store.persist(package)
        except Exception as e:
            logger.exception("Pipeline failed for %s: %s", package.title, str(e))
            package.state = IngestionState.FAILED
            raise
