import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Text, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from backend.core.database import Base
from backend.models.run_ledger import RunLedgerMixin, RunStatus

class ReasoningExecution(RunLedgerMixin, Base):
    """
    SQLAlchemy model to track and persist the execution lifecycle 
    of a reasoning task, enabling durable workflows and suspend/resume actions.
    """
    __tablename__ = "reasoning_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    
    # State flags: running, suspended, completed, failed
    status = Column(String, default="running", nullable=False)
    
    current_task_index = Column(Integer, default=0, nullable=False)
    stats = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # JSON dump of the ReasoningState dict
    state_snapshot = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    async def latest_for_subject(cls, session: AsyncSession, workspace_id: str) -> Optional["ReasoningExecution"]:
        """Query the latest reasoning execution for the given workspace."""
        stmt = (
            select(cls)
            .where(cls.workspace_id == workspace_id)
            .order_by(cls.created_at.desc())
        )
        return (await session.execute(stmt)).scalars().first()

    def __repr__(self):
        return f"<ReasoningExecution(id='{self.id}', status='{self.status}', query='{self.query[:30]}...')>"

