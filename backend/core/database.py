"""
Assest — Database Connection & Session Management
Uses SQLite (aiosqlite) for development, PostgreSQL (asyncpg) for production.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text, event
from sqlalchemy.orm import DeclarativeBase
from backend.core.config import get_settings
from uuid import uuid4

settings = get_settings()

# ── Engine ──────────────────────────────────────────────
# SQLite needs connect_args for async; PostgreSQL (asyncpg) requires special SSL handling
_connect_args = {}
db_url = settings.database_url

import os
if os.getenv("ASSEST_DEV_MODE") == "sandbox":
    print("🧪 Sandbox Mode: Using local SQLite database.")
    db_url = "sqlite+aiosqlite:///./data/sandbox.db"

if db_url.startswith("sqlite"):
    _connect_args = {
        "check_same_thread": False,
        "timeout": 60,
    }
elif "postgresql" in db_url or db_url.startswith("postgres://"):
    # Fix scheme for asyncpg if it's missing
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

    # PgBouncer (used by Supabase/managed DBs) does not support prepared statements
    # in 'transaction' or 'statement' pooling modes.
    # We must disable them by setting statement_cache_size AND prepared_statement_cache_size to 0.
    _connect_args["statement_cache_size"] = 0
    _connect_args["prepared_statement_cache_size"] = 0

    # asyncpg does not support 'sslmode' in the URL or as a connect_arg.
    # We must strip it and pass 'ssl' context/bool in connect_args instead.
    if "sslmode=" in db_url:
        import re
        db_url = re.sub(r"[?&]sslmode=[^&]+", "", db_url)

    # For Supabase/managed DBs, we often need to allow self-signed certs
    # or just require SSL without strict verification in some dev environments.
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    _connect_args["ssl"] = ctx


from sqlalchemy.pool import NullPool

if "postgresql" in db_url:
    engine = create_async_engine(
        db_url,
        echo=settings.sql_echo,
        connect_args=_connect_args,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        db_url,
        echo=settings.sql_echo,
        connect_args=_connect_args,
    )

# Enable WAL mode for SQLite to prevent database lock errors
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

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
        # Note: Explicit Enum names in models prevent "Type already exists" errors in PostgreSQL
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            from backend.core.migrations import ensure_sqlite_dev_columns, ensure_sqlite_dev_indexes
            await ensure_sqlite_dev_columns(conn)
            await ensure_sqlite_dev_indexes(conn)


async def close_db():
    """Dispose engine connections. Called on app shutdown."""
    await engine.dispose()



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
