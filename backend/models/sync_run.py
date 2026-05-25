from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, select
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from backend.core.database import Base
from backend.models.run_ledger import RunLedgerMixin, RunStatus
import uuid


class SyncRunStatus(RunStatus):
    ACTIVE = {RunStatus.QUEUED, RunStatus.RUNNING}


class SyncRun(RunLedgerMixin, Base):
    """
    Product-facing record for one connector sync attempt.
    BackgroundTask is the execution adapter; SyncRun is the user-visible truth.
    """
    __tablename__ = "sync_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    connector_id = Column(String, ForeignKey("connectors.id"), nullable=False, index=True)
    workspace_id = Column(String, nullable=False, index=True)
    triggered_by = Column(String, nullable=False, default="manual")
    selected_ids = Column(JSON, nullable=True)
    task_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default=SyncRunStatus.QUEUED, index=True)
    stats = Column(JSON, default=dict)
    error = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    connector = relationship("Connector")

    @classmethod
    async def latest_for_subject(cls, session: AsyncSession, connector_id: str) -> Optional["SyncRun"]:
        """Query the latest sync run for the given connector."""
        stmt = (
            select(cls)
            .where(cls.connector_id == connector_id)
            .order_by(cls.created_at.desc())
        )
        return (await session.execute(stmt)).scalars().first()

    def __repr__(self):
        return f"<SyncRun(id='{self.id}', connector_id='{self.connector_id}', status='{self.status}')>"

