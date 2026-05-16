"""
Assest — Database Connection & Session Management
Uses SQLite (aiosqlite) for development, PostgreSQL (asyncpg) for production.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase
from backend.core.config import get_settings

settings = get_settings()

# ── Engine ──────────────────────────────────────────────
# SQLite needs connect_args for async; PostgreSQL does not
_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
    connect_args=_connect_args,
)

# ── Session Factory ─────────────────────────────────────
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ──────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# ── Dependency ──────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides a database session.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Lifecycle ───────────────────────────────────────────
async def init_db():
    """Create all tables. Called on app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            await _ensure_sqlite_dev_columns(conn)


async def close_db():
    """Dispose engine connections. Called on app shutdown."""
    await engine.dispose()


async def _ensure_sqlite_dev_columns(conn):
    """
    Additive schema sync for local SQLite development.
    SQLAlchemy create_all creates missing tables but does not migrate existing ones.
    """
    table_columns = {
        "chunks": {
            "parent_id": "VARCHAR",
            "heading_path": "JSON",
            "chunk_type": "VARCHAR DEFAULT 'text'",
            "structural_metadata": "JSON",
            "content_tokens": "INTEGER DEFAULT 0",
            "search_content": "TEXT",
            "tier": "INTEGER DEFAULT 2",
            "source_type": "VARCHAR",
            "source_url": "VARCHAR",
            "document_title": "VARCHAR",
            "permissions": "JSON",
            "quality_score": "FLOAT DEFAULT 1.0",
            "retrieval_count": "INTEGER DEFAULT 0",
            "positive_feedback": "INTEGER DEFAULT 0",
            "negative_feedback": "INTEGER DEFAULT 0",
            "source_modified_at": "DATETIME",
            "expires_at": "DATETIME",
            "created_at": "DATETIME",
        },
        "documents": {
            "document_type": "VARCHAR DEFAULT 'general'",
            "mime_type": "VARCHAR",
            "tier": "INTEGER DEFAULT 2",
            "tags": "JSON",
            "is_stale": "BOOLEAN DEFAULT 0",
        },
        "connectors": {
            "last_sync_cursor": "VARCHAR",
            "error_log": "JSON",
        },
        "query_logs": {
            "conversation_id": "VARCHAR",
            "feedback": "VARCHAR DEFAULT 'NULL'",
            "response_time_ms": "INTEGER",
        },
    }

    for table_name, columns in table_columns.items():
        existing = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        existing_names = {row[1] for row in existing.fetchall()}
        for column_name, column_type in columns.items():
            if column_name not in existing_names:
                await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


# ── Idempotent Operations (Phase 3a: Event-Driven Sync) ────
from typing import TypeVar, Type, Optional, Dict, Any
from sqlalchemy import select
from datetime import datetime

ModelT = TypeVar("ModelT")


async def upsert_idempotent(
    session: AsyncSession,
    model_class: Type[ModelT],
    lookup_fields: Dict[str, Any],
    update_fields: Dict[str, Any],
    idempotency_key: Optional[str] = None
) -> tuple[ModelT, bool]:
    """
    Idempotent upsert operation.
    
    If record exists (by lookup_fields), merge update_fields.
    If record doesn't exist, create it.
    
    Uses idempotency_key to prevent duplicate processing of same event.
    
    Args:
        session: AsyncSession
        model_class: SQLAlchemy model class
        lookup_fields: Dict of fields to find existing record (e.g., {"source_id": "123"})
        update_fields: Dict of fields to update/set
        idempotency_key: Optional unique key for idempotency (prevents reprocessing)
    
    Returns:
        Tuple of (model_instance, is_new_record)
    
    Example:
        record, is_new = await upsert_idempotent(
            db,
            CanonicalSection,
            lookup_fields={"source_id": "page_123", "workspace_id": "w_456"},
            update_fields={
                "content": "...",
                "updated_at": datetime.now(),
                "source_version": 2
            },
            idempotency_key="event_xyz"
        )
    """
    # Query for existing record
    stmt = select(model_class)
    for field_name, field_value in lookup_fields.items():
        stmt = stmt.where(getattr(model_class, field_name) == field_value)
    
    result = await session.execute(stmt)
    existing = result.scalars().first()
    
    if existing:
        # Update existing record
        for field_name, field_value in update_fields.items():
            setattr(existing, field_name, field_value)
        
        # Add idempotency key if provided
        if idempotency_key and hasattr(existing, "idempotency_key"):
            existing.idempotency_key = idempotency_key
        
        await session.flush()
        return existing, False
    
    else:
        # Create new record
        new_record = model_class(**lookup_fields, **update_fields)
        
        # Add idempotency key if provided
        if idempotency_key and hasattr(new_record, "idempotency_key"):
            new_record.idempotency_key = idempotency_key
        
        session.add(new_record)
        await session.flush()
        return new_record, True


async def soft_delete(
    session: AsyncSession,
    model_instance: ModelT,
    deleted_by: Optional[str] = None,
    deleted_reason: Optional[str] = None
) -> None:
    """
    Soft delete a record (mark deleted, keep in database).
    
    Args:
        session: AsyncSession
        model_instance: Instance to soft delete
        deleted_by: Who deleted it (e.g., "system", "user_123", "webhook_notion")
        deleted_reason: Why it was deleted
    
    Example:
        await soft_delete(
            db,
            canonical_section,
            deleted_by="webhook_notion",
            deleted_reason="Page deleted in Notion"
        )
    """
    if hasattr(model_instance, "deleted_at"):
        model_instance.deleted_at = datetime.utcnow()
    
    if hasattr(model_instance, "deleted_by") and deleted_by:
        model_instance.deleted_by = deleted_by
    
    if hasattr(model_instance, "deleted_reason") and deleted_reason:
        model_instance.deleted_reason = deleted_reason
    
    await session.flush()
