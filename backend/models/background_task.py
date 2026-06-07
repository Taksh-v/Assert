from datetime import datetime
from sqlalchemy import Column, String, JSON, Integer, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from backend.core.database import Base
from backend.models.run_ledger import RunLedgerMixin, RunStatus
import uuid

class BackgroundTask(RunLedgerMixin, Base):
    """
    Model for tracking background tasks in a resilient queue.
    """
    __tablename__ = "background_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_type = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String, default="pending", index=True)  # pending, processing, failed, completed
    retry_count = Column(Integer, default=0)
    error_log = Column(JSON, nullable=True)
    stats = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Status mapping to translate canonical statuses to Task Queue terms
    _STATUS_MAP = {
        RunStatus.QUEUED: "pending",
        RunStatus.RUNNING: "processing",
        RunStatus.COMPLETED: "completed",
        RunStatus.FAILED: "failed",
    }
    _REVERSE_STATUS_MAP = {v: k for k, v in _STATUS_MAP.items()}

    def _set_error(self, error: Optional[str]) -> None:
        """Custom error handler to log failures in error_log JSON format."""
        if error is None:
            return
        error_str = str(error)
        error_info = {
            "error": error_str,
            "timestamp": datetime.utcnow().isoformat(),
            "attempt": self.retry_count
        }
        if not self.error_log:
            self.error_log = {"errors": []}
        current_log = dict(self.error_log)
        if "errors" not in current_log:
            current_log["errors"] = []
        else:
            current_log["errors"] = list(current_log["errors"])
        current_log["errors"].append(error_info)
        self.error_log = current_log

    @classmethod
    async def latest_for_subject(cls, session: AsyncSession, task_type: str) -> Optional["BackgroundTask"]:
        """Query the latest background task of a given type."""
        stmt = (
            select(cls)
            .where(cls.task_type == task_type)
            .order_by(cls.created_at.desc())
        )
        return (await session.execute(stmt)).scalars().first()

    def __repr__(self):
        return f"<BackgroundTask(id='{self.id}', type='{self.task_type}', status='{self.status}')>"

