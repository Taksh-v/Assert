import logging
import asyncio
from typing import Any, Optional

from backend.ingestion.document_run import IngestionPackage, IngestionState, DocumentIngestionError
from backend.ingestion.document_store import DocumentStore
from backend.ingestion.index_adapter import IndexAdapter
from backend.ingestion.metrics import timer, run_with_timeout
from typing import Optional
from backend.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class IngestionRunner:
    def __init__(
        self,
        document_store: Optional[DocumentStore] = None,
        index_adapter: Optional[IndexAdapter] = None,
        templates: Optional[dict[str, Any]] = None,
        default_template: Optional[Any] = None,
        memory_store: Optional[MemoryStore] = None,
    ) -> None:
        self.document_store = document_store
        self.index_adapter = index_adapter
        self.templates = templates or {}
        self.default_template = default_template
        self.memory_store = memory_store

    def select_template(self, package: IngestionPackage) -> Optional[Any]:
        doc_type = package.metadata.get("document_type")
        if doc_type and doc_type.lower() in self.templates:
            return self.templates[doc_type.lower()]

        source_type = getattr(package.raw_doc, "source_type", None)
        if source_type and source_type.lower() in self.templates:
            return self.templates[source_type.lower()]

        source_url = getattr(package.raw_doc, "source_url", "").lower()
        if source_url:
            import urllib.parse
            import os
            try:
                parsed_url = urllib.parse.urlparse(source_url)
                ext = os.path.splitext(parsed_url.path)[1].lstrip(".")
                if ext and ext in self.templates:
                    return self.templates[ext]
            except Exception:
                pass

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
        async def _process():
            try:
                # record start in memory store if available
                if getattr(self, "memory_store", None):
                    try:
                        await self.memory_store.set(f"package:{package.workspace_id}:{package.title}:state", "started")
                    except Exception:
                        logger.exception("Failed to write start state to memory store")

                with timer(f"ingestion.transform.{package.title}"):
                    for transformer in template.transformers:
                        await transformer.transform(package)

                # Fine-grained timers for persistence and indexing stages
                if self.document_store:
                    with timer(f"ingestion.prepare_version.{package.title}"):
                        version_plan = await self.document_store.prepare_version(package.raw_doc, package.workspace_id)
                    if getattr(version_plan, "should_skip", False):
                        package.state = IngestionState.PERSISTED
                        return

                    # Build payloads first so they are available for both vector store and DB bundle writes
                    payloads = []
                    if package.chunks:
                        payloads = [
                            {
                                "title": package.title,
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
                        with timer(f"ingestion.persist_document_bundle.{package.title}"):
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
                    else:
                        with timer(f"ingestion.persist_document.{package.title}"):
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
                        if package.chunks:
                            with timer(f"ingestion.persist_chunks.{package.title}"):
                                await self.document_store.persist_chunks(
                                    document_id=doc_record.id,
                                    workspace_id=package.workspace_id,
                                    chunks=package.chunks,
                                    payloads=payloads,
                                    version=version_plan.current_version,
                                )
                    package.doc_record = doc_record

                    # index embeddings with fully populated payloads
                    if package.embeddings and self.index_adapter:
                        with timer(f"ingestion.index_vectors.{package.title}"):
                            await self.index_adapter.upsert_vectors(package.workspace_id, package.embeddings, payloads)

                    # Update dynamic BM25 sparse indexer in-memory
                    try:
                        from backend.query.sparse_indexer import get_sparse_indexer
                        import uuid
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

                    # graph artifacts
                    resolved_entities = package.metadata.get("entities", [])
                    extracted_events = package.metadata.get("events", [])
                    if self.index_adapter:
                        with timer(f"ingestion.graph_artifacts.{package.title}"):
                            await self.index_adapter.add_graph_artifacts(package.workspace_id, doc_record.id, resolved_entities, extracted_events)

                package.state = IngestionState.PERSISTED
                if getattr(self, "memory_store", None):
                    try:
                        await self.memory_store.set(f"package:{package.workspace_id}:{package.title}:state", "persisted")
                    except Exception:
                        logger.exception("Failed to write persisted state to memory store")
            except Exception as e:
                logger.exception("Pipeline failed for %s: %s", package.title, str(e))
                package.state = IngestionState.FAILED
                if getattr(self, "memory_store", None):
                    try:
                        await self.memory_store.set(f"package:{package.workspace_id}:{package.title}:state", "failed")
                    except Exception:
                        logger.exception("Failed to write failed state to memory store")
                raise

        # run the processing with a default timeout to prevent stuck pipelines
        try:
            await run_with_timeout(_process(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.exception("Pipeline timed out for %s", package.title)
            package.state = IngestionState.FAILED
            raise

    def close(self) -> None:
        if self.index_adapter:
            try:
                self.index_adapter.close()
            except Exception:
                pass
