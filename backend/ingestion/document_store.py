import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Protocol

from sqlalchemy import update, select

from backend.core.database import async_session
from backend.models.chunk import Chunk as DBChunk
from backend.models.document import Document
from backend.models.knowledge_event import KnowledgeEvent


@dataclass
class VersionPlan:
    current_version: int = 1
    previous_document_id: Optional[str] = None
    should_skip: bool = False


class DocumentStore(Protocol):
    async def prepare_version(self, raw_doc: Any, workspace_id: str) -> VersionPlan:
        ...

    async def persist_document(
        self,
        raw_doc: Any,
        workspace_id: str,
        connector_id: Optional[str],
        doc_type: str,
        content_hash: str,
        chunk_count: int,
        tier: int,
        tags: list[str],
        version: int,
        previous_document_id: Optional[str],
    ) -> Document:
        ...

    async def persist_chunks(
        self,
        document_id: str,
        workspace_id: str,
        chunks: list[str],
        payloads: list[dict[str, Any]],
        version: int,
    ) -> None:
        ...

    async def persist_events(
        self,
        workspace_id: str,
        document_id: str,
        events: list[dict[str, Any]],
    ) -> None:
        ...


class SQLDocumentStore:
    async def prepare_version(self, raw_doc: Any, workspace_id: str) -> VersionPlan:
        async with async_session() as session:
            stmt = select(Document).where(
                Document.source_url == getattr(raw_doc, "source_url", ""),
                Document.workspace_id == workspace_id,
                Document.is_active == True,
            )
            res = await session.execute(stmt)
            existing_doc = res.scalars().first()

            if not existing_doc:
                return VersionPlan()

            if hasattr(raw_doc, "content_hash") and existing_doc.content_hash == raw_doc.content_hash:
                # Verify that chunks actually exist — a previous partial failure
                # may have written the document metadata but failed before persisting
                # chunks / embeddings, leaving the system in a permanently stuck state.
                chunk_count_stmt = select(DBChunk.id).where(
                    DBChunk.document_id == existing_doc.id,
                    DBChunk.is_active == True,
                ).limit(1)
                chunk_res = await session.execute(chunk_count_stmt)
                has_chunks = chunk_res.scalars().first() is not None

                if has_chunks:
                    return VersionPlan(should_skip=True)

                # Chunks missing — treat existing metadata as stale and force
                # a clean re-ingestion by deactivating the zombie record.
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning(
                    f"Document '{existing_doc.id}' has matching content_hash but "
                    f"zero active chunks; deactivating stale record and forcing re-ingestion."
                )
                existing_doc.is_active = False
                await session.commit()
                return VersionPlan(
                    current_version=existing_doc.version + 1,
                    previous_document_id=existing_doc.id,
                )

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

    async def persist_document(
        self,
        raw_doc: Any,
        workspace_id: str,
        connector_id: Optional[str],
        doc_type: str,
        content_hash: str,
        chunk_count: int,
        tier: int,
        tags: list[str],
        version: int,
        previous_document_id: Optional[str],
    ) -> Document:
        async with async_session() as session:
            doc_record = Document(
                workspace_id=workspace_id,
                connector_id=connector_id,
                source_url=getattr(raw_doc, "source_url", ""),
                title=getattr(raw_doc, "title", "Untitled"),
                document_type=doc_type,
                content_hash=content_hash,
                chunk_count=chunk_count,
                tier=tier,
                tags=tags,
                version=version,
                previous_version_id=previous_document_id,
                is_active=True,
            )
            doc_record = await session.merge(doc_record)
            await session.commit()
            await session.refresh(doc_record)
            return doc_record

    async def persist_document_bundle(
        self,
        raw_doc: Any,
        workspace_id: str,
        connector_id: Optional[str],
        doc_type: str,
        content_hash: str,
        chunk_count: int,
        tier: int,
        tags: list[str],
        version: int,
        previous_document_id: Optional[str],
        chunks: list[str],
        payloads: list[dict[str, Any]],
    ) -> Document:
        async with async_session() as session:
            doc_record = Document(
                workspace_id=workspace_id,
                connector_id=connector_id,
                source_url=getattr(raw_doc, "source_url", ""),
                title=getattr(raw_doc, "title", "Untitled"),
                document_type=doc_type,
                content_hash=content_hash,
                chunk_count=chunk_count,
                tier=tier,
                tags=tags,
                version=version,
                previous_version_id=previous_document_id,
                is_active=True,
            )
            doc_record = await session.merge(doc_record)

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
                    version=version,
                    is_active=True,
                )
                await session.merge(new_chunk)

            await session.commit()
            await session.refresh(doc_record)
            return doc_record

    async def persist_chunks(
        self,
        document_id: str,
        workspace_id: str,
        chunks: list[str],
        payloads: list[dict[str, Any]],
        version: int,
    ) -> None:
        async with async_session() as session:
            for idx, chunk_text in enumerate(chunks):
                c_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{idx}"))
                payload = payloads[idx]
                new_chunk = DBChunk(
                    id=c_id,
                    document_id=document_id,
                    workspace_id=workspace_id,
                    content=chunk_text,
                    chunk_index=idx,
                    tier=payload.get("content_tier", 2),
                    source_type=payload.get("source_type"),
                    source_url=payload.get("source_url"),
                    document_title=payload.get("title"),
                    version=version,
                    is_active=True,
                )
                await session.merge(new_chunk)
            await session.commit()

    async def persist_events(
        self,
        workspace_id: str,
        document_id: str,
        events: list[dict[str, Any]],
    ) -> None:
        if not events:
            return

        async with async_session() as session:
            for event_data in events:
                new_event = KnowledgeEvent(
                    workspace_id=workspace_id,
                    event_type=event_data.get("type", "milestone"),
                    title=event_data.get("title", "Unknown Event"),
                    description=event_data.get("description"),
                    timestamp=datetime.utcnow(),
                    source_document_id=document_id,
                    metadata_json=event_data,
                )
                session.add(new_event)
            await session.commit()
