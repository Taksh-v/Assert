import logging
import base64
from typing import Dict, Any, List
from temporalio import activity
from sqlalchemy import select

from backend.core.database import async_session
from backend.core.security import decrypt_config
from backend.connectors.registry import connector_factory
from backend.models.connector import Connector, ConnectorStatus
from backend.models.failed_ingestion import FailedIngestion
from backend.ingestion.pipeline import IngestionPipeline
from backend.ingestion.document_run import IngestionPackage, IngestionState
from backend.ingestion.pipeline_v2 import ChunkerTransformer, EmbedderTransformer

logger = logging.getLogger(__name__)


class DictLike(dict):
    def __getattr__(self, name: str) -> Any:
        if name in self:
            return self[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


@activity.defn
async def fetch_documents_activity(connector_id: str) -> List[Dict[str, Any]]:
    logger.info(f"Fetching documents for connector: {connector_id}")
    serialized_docs = []

    async with async_session() as session:
        stmt = select(Connector).where(Connector.id == connector_id)
        res = await session.execute(stmt)
        connector = res.scalars().first()
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")

        if connector.status != ConnectorStatus.ACTIVE:
            logger.info(f"Connector {connector_id} is not active")
            return []

        workspace_id = connector.workspace_id

        decrypted_config = decrypt_config(connector.config)
        conn_type = connector.type.value if hasattr(connector.type, "value") else str(connector.type)

        try:
            conn_impl = connector_factory.create(conn_type)
        except Exception as e:
            logger.exception(f"Failed to create connector implementation for {conn_type}")
            raise e

        try:
            connection = await conn_impl.connect(decrypted_config)
        except Exception as e:
            logger.exception(f"Failed to connect to connector {connector_id}")
            raise e

        try:
            docs_generator = conn_impl.fetch_documents(connection)

            def serialize_doc(raw_doc) -> Dict[str, Any]:
                raw_content = getattr(raw_doc, "raw_content", getattr(raw_doc, "content", ""))
                if isinstance(raw_content, bytes):
                    content_val = base64.b64encode(raw_content).decode("utf-8")
                    is_base64 = True
                else:
                    content_val = str(raw_content)
                    is_base64 = False

                return {
                    "source_id": getattr(raw_doc, "source_id", "unknown"),
                    "title": getattr(raw_doc, "title", "Untitled"),
                    "raw_content": content_val,
                    "content": content_val,
                    "is_base64": is_base64,
                    "source_url": getattr(raw_doc, "source_url", ""),
                    "metadata": getattr(raw_doc, "metadata", {}),
                    "permissions": getattr(raw_doc, "permissions", []),
                    "content_format": getattr(raw_doc, "content_format", "text"),
                    "tier": getattr(raw_doc, "tier", 2),
                    "content_hash": getattr(raw_doc, "content_hash", ""),
                    "workspace_id": workspace_id,
                    "connector_id": connector_id,
                    "source_type": conn_type,
                }

            if hasattr(docs_generator, "__aiter__"):
                async for raw_doc in docs_generator:
                    serialized_docs.append(serialize_doc(raw_doc))
            else:
                for raw_doc in docs_generator:
                    serialized_docs.append(serialize_doc(raw_doc))
        except Exception as e:
            logger.exception(f"Failed to fetch documents for connector {connector_id}")
            raise e

    return serialized_docs


@activity.defn
async def scrub_document_activity(doc_payload: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Scrubbing document: {doc_payload.get('source_url', 'unknown')}")

    # Reconstruct raw content if base64 encoded
    raw_doc_dict = doc_payload.copy()
    if raw_doc_dict.get("is_base64"):
        raw_doc_dict["raw_content"] = base64.b64decode(raw_doc_dict["raw_content"].encode("utf-8"))
    raw_doc = DictLike(raw_doc_dict)

    pipeline = IngestionPipeline()
    package = IngestionPackage(
        raw_doc=raw_doc,
        workspace_id=raw_doc.get("workspace_id", ""),
        connector_id=raw_doc.get("connector_id", "")
    )

    template = pipeline.runner.select_template(package)
    if not template:
        raise ValueError("No matching ingestion template found")

    for transformer in template.transformers:
        if isinstance(transformer, (ChunkerTransformer, EmbedderTransformer)):
            continue
        await transformer.transform(package)

    return {
        "title": package.title,
        "content": package.content,
        "elements": package.elements,
        "metadata": package.metadata,
        "raw_doc": doc_payload,
    }


@activity.defn
async def index_document_activity(scrubbed: Dict[str, Any], workspace_id: str, connector_id: str) -> Dict[str, Any]:
    logger.info(f"Indexing document: {scrubbed.get('title', 'Untitled')}")

    raw_doc_dict = scrubbed["raw_doc"].copy()
    if raw_doc_dict.get("is_base64"):
        raw_doc_dict["raw_content"] = base64.b64decode(raw_doc_dict["raw_content"].encode("utf-8"))
    raw_doc = DictLike(raw_doc_dict)

    pipeline = IngestionPipeline()
    package = IngestionPackage(
        raw_doc=raw_doc,
        workspace_id=workspace_id,
        connector_id=connector_id
    )
    package.title = scrubbed["title"]
    package.content = scrubbed["content"]
    package.elements = scrubbed["elements"]
    package.metadata = scrubbed["metadata"]
    package.state = IngestionState.ENRICHED

    template = pipeline.runner.select_template(package)
    if not template:
        raise ValueError("No matching template found")

    for transformer in template.transformers:
        if isinstance(transformer, (ChunkerTransformer, EmbedderTransformer)):
            await transformer.transform(package)

    runner = pipeline.runner
    if runner.document_store:
        version_plan = await runner.document_store.prepare_version(package.raw_doc, package.workspace_id)
        if getattr(version_plan, "should_skip", False):
            package.state = IngestionState.PERSISTED
        else:
            doc_record = await runner.document_store.persist_document(
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

            # index embeddings
            if package.embeddings and runner.index_adapter:
                await runner.index_adapter.upsert_vectors(package.workspace_id, package.embeddings, [{} for _ in package.embeddings])

            # persist chunks
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
                await runner.document_store.persist_chunks(
                    document_id=doc_record.id,
                    workspace_id=package.workspace_id,
                    chunks=package.chunks,
                    payloads=payloads,
                    version=version_plan.current_version,
                )
            package.state = IngestionState.PERSISTED

    doc_id = package.doc_record.id if package.doc_record else None
    return {
        "document_id": doc_id,
        "title": package.title,
        "source_url": raw_doc.get("source_url", ""),
        "entities": package.metadata.get("entities", []),
        "events": package.metadata.get("events", []),
        "should_skip": package.state == IngestionState.PERSISTED and not package.doc_record,
    }


@activity.defn
async def build_graph_activity(index_result: Dict[str, Any], workspace_id: str) -> None:
    if index_result.get("should_skip") or not index_result.get("document_id"):
        return

    logger.info(f"Building graph artifacts for: {index_result.get('title', 'Untitled')}")

    pipeline = IngestionPipeline()
    runner = pipeline.runner

    doc_id = index_result["document_id"]
    resolved_entities = index_result.get("entities", [])
    extracted_events = index_result.get("events", [])

    if runner.index_adapter:
        await runner.index_adapter.add_graph_artifacts(workspace_id, doc_id, resolved_entities, extracted_events)


@activity.defn
async def record_failed_ingestion_activity(
    workspace_id: str,
    source_type: str,
    source_url: str,
    error_message: str
) -> None:
    logger.info(f"Recording failed ingestion to DLQ: {source_url}")
    async with async_session() as session:
        failed = FailedIngestion(
            workspace_id=workspace_id,
            source_type=source_type,
            source_url=source_url,
            error_message=error_message,
            status="pending"
        )
        session.add(failed)
        await session.commit()
