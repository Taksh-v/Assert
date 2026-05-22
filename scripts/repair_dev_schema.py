"""
Repair the local development database schema.

This helper is safe for the default SQLite dev database used by this repo.
It first runs the normal `init_db()` bootstrap, then rebuilds the
`failed_ingestions` table if `retry_count` still has the legacy JSON type.
"""

import asyncio
import logging
from sqlalchemy import text

from backend.core.config import get_settings
from backend.core.database import async_session, init_db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair_dev_schema")


async def _table_info(conn, table_name: str) -> list[tuple]:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    return list(result.fetchall())


async def _repair_failed_ingestions_sqlite() -> None:
    """Rebuild failed_ingestions so retry_count is INTEGER instead of JSON."""
    async with async_session() as session:
        conn = await session.connection()
        columns = await _table_info(conn, "failed_ingestions")
        column_map = {col[1]: col for col in columns}

        retry_column = column_map.get("retry_count")
        if retry_column and str(retry_column[2]).upper() == "INTEGER":
            logger.info("failed_ingestions.retry_count is already INTEGER; no repair needed.")
            return

        logger.info("Repairing failed_ingestions.retry_count to INTEGER...")

        await conn.execute(text("DROP TABLE IF EXISTS failed_ingestions_new"))
        await conn.execute(
            text(
                """
                CREATE TABLE failed_ingestions_new (
                    id VARCHAR PRIMARY KEY NOT NULL,
                    workspace_id VARCHAR NOT NULL,
                    source_type VARCHAR NOT NULL,
                    source_url VARCHAR NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT,
                    raw_payload JSON,
                    attempts JSON,
                    retry_count INTEGER DEFAULT 0,
                    status VARCHAR DEFAULT 'pending',
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO failed_ingestions_new (
                    id, workspace_id, source_type, source_url, error_message,
                    stack_trace, raw_payload, attempts, retry_count, status,
                    created_at, updated_at
                )
                SELECT
                    id,
                    workspace_id,
                    source_type,
                    source_url,
                    error_message,
                    stack_trace,
                    raw_payload,
                    attempts,
                    CASE
                        WHEN retry_count IS NULL THEN 0
                        ELSE CAST(retry_count AS INTEGER)
                    END,
                    COALESCE(status, 'pending'),
                    created_at,
                    updated_at
                FROM failed_ingestions
                """
            )
        )
        await conn.execute(text("DROP TABLE failed_ingestions"))
        await conn.execute(text("ALTER TABLE failed_ingestions_new RENAME TO failed_ingestions"))
        await session.commit()
        logger.info("failed_ingestions table repaired successfully.")


async def main() -> None:
    settings = get_settings()
    logger.info("Initializing database schema...")
    await init_db()

    if settings.database_url.startswith("sqlite"):
        await _repair_failed_ingestions_sqlite()
    else:
        logger.info("Non-SQLite database detected; no local repair needed.")


if __name__ == "__main__":
    asyncio.run(main())