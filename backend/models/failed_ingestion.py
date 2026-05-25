from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Text, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from backend.core.database import Base
from backend.models.run_ledger import RunLedgerMixin, RunStatus
import uuid

class FailedIngestion(RunLedgerMixin, Base):
    """
    Blueprint Layer 13: Dead Letter Queue (DLQ).
    Stores details of failed document ingests for debugging and retries.
    """
    __tablename__ = "failed_ingestions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False)
    
    source_type = Column(String, nullable=False) # slack, notion, drive
    source_url = Column(String, nullable=False)
    
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    
    # Stores the raw data if available for replay
    raw_payload = Column(JSON, nullable=True)
    
    attempts = Column(JSON, default=list) # List of timestamps and errors
    retry_count = Column(Integer, default=0)
    stats = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    status = Column(String, default="pending") # pending, retrying, failed, resolved
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Status mapping to translate canonical statuses to DLQ terms
    _STATUS_MAP = {
        RunStatus.QUEUED: "pending",
        RunStatus.RUNNING: "retrying",
        RunStatus.COMPLETED: "resolved",
        RunStatus.FAILED: "failed",
    }
    _REVERSE_STATUS_MAP = {v: k for k, v in _STATUS_MAP.items()}

    @classmethod
    async def latest_for_subject(cls, session: AsyncSession, source_url: str) -> Optional["FailedIngestion"]:
        """Query the latest failed ingestion for the given source URL."""
        stmt = (
            select(cls)
            .where(cls.source_url == source_url)
            .order_by(cls.created_at.desc())
        )
        return (await session.execute(stmt)).scalars().first()

    def __repr__(self):
        return f"<FailedIngestion(source='{self.source_type}', url='{self.source_url}')>"

