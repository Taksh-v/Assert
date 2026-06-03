"""
Additive schema migration helpers for local SQLite development.
"""


import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

async def ensure_sqlite_dev_columns(conn):
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
        "connector_sync_states": {
            "last_sync_token": "VARCHAR",
            "last_stats": "JSON",
            "is_running": "BOOLEAN DEFAULT 0",
            "lock_owner": "VARCHAR",
            "lock_acquired_at": "DATETIME",
            "lock_expires_at": "DATETIME",
            "last_error": "TEXT",
        },
        "failed_ingestions": {
            "attempts": "JSON",
            "retry_count": "INTEGER DEFAULT 0",
            "stats": "JSON",
            "started_at": "DATETIME",
            "completed_at": "DATETIME",
            "status": "VARCHAR DEFAULT 'pending'",
        },
        "query_logs": {
            "conversation_id": "VARCHAR",
            "feedback": "VARCHAR DEFAULT 'NULL'",
            "response_time_ms": "INTEGER",
            "request_id": "VARCHAR",
            "faithfulness_score": "FLOAT",
            "relevance_score": "FLOAT",
            "eval_reasoning": "TEXT",
        },
        "knowledge_objects": {
            "title": "VARCHAR",
            "type": "VARCHAR",
            "summary": "TEXT",
            "entities": "JSON",
            "topics": "JSON",
            "source_document_ids": "JSON",
            "relationships": "JSON",
        },
        "background_tasks": {
            "task_type": "VARCHAR",
            "payload": "JSON",
            "status": "VARCHAR DEFAULT 'pending'",
            "retry_count": "INTEGER DEFAULT 0",
            "error_log": "JSON",
            "stats": "JSON",
            "started_at": "DATETIME",
            "completed_at": "DATETIME",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "sync_runs": {
            "connector_id": "VARCHAR",
            "workspace_id": "VARCHAR",
            "triggered_by": "VARCHAR DEFAULT 'manual'",
            "selected_ids": "JSON",
            "task_id": "VARCHAR",
            "status": "VARCHAR DEFAULT 'queued'",
            "stats": "JSON",
            "error": "VARCHAR",
            "started_at": "DATETIME",
            "completed_at": "DATETIME",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "reasoning_executions": {
            "stats": "JSON",
            "started_at": "DATETIME",
            "completed_at": "DATETIME",
            "request_id": "VARCHAR",
        }
    }

    for table_name, columns in table_columns.items():
        existing = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        existing_names = {row[1] for row in existing.fetchall()}
        for column_name, column_type in columns.items():
            if column_name not in existing_names:
                logger.info(f"Adding missing column {column_name} ({column_type}) to table {table_name}")
                await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
