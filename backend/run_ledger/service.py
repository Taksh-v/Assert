"""
RunLedger Service Facade

Provides a small facade over RunLedger model transitions so callers
use a single code path for lifecycle changes. This keeps transition
logic centralized and makes it easier to audit, test, and evolve.
"""
from datetime import datetime
from typing import Any, Dict, Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.run_ledger import RunStatus


class RunLedgerService:
    """Facade for run lifecycle operations.

    Usage:
        await RunLedgerService.finish_run(session, SyncRun, run_id, RunStatus.COMPLETED)
    """

    @staticmethod
    async def finish_run(
        session: AsyncSession,
        model_cls: Type,
        run_id: str,
        status: str,
        *,
        stats: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Load the run record, perform the canonical transition, and flush.

        This intentionally keeps DB mutation in the caller-provided session so
        callers can continue to update related tables in the same transaction.
        """
        result = await session.execute(select(model_cls).where(model_cls.id == run_id))
        run = result.scalars().first()
        if not run:
            raise ValueError(f"Run {run_id} not found for {model_cls}")

        # Map status to transition methods on the mixin
        if status == RunStatus.COMPLETED:
            run.mark_completed(stats=stats)
        elif status == RunStatus.COMPLETED_WITH_ERRORS:
            run.mark_completed_with_errors(stats=stats, error=error)
        elif status == RunStatus.FAILED:
            run.mark_failed(error=error)
        elif status == RunStatus.CANCELLED:
            run.mark_cancelled()
        elif status == RunStatus.RUNNING:
            if run.canonical_status != RunStatus.RUNNING:
                run.mark_started()
        elif status == RunStatus.SUSPENDED:
            run.mark_suspended()
        else:
            # Fallback: set raw status if model allows it
            run.status = status
            if stats is not None and hasattr(run, "stats"):
                run.stats = stats

        # Persist transient changes to the SQLAlchemy identity
        await session.flush()
        return run

    @staticmethod
    async def heartbeat(session: AsyncSession, model_cls: Type, run_id: str):
        result = await session.execute(select(model_cls).where(model_cls.id == run_id))
        run = result.scalars().first()
        if not run:
            raise ValueError(f"Run {run_id} not found for {model_cls}")
        run.heartbeat()
        await session.flush()
        return run

    @staticmethod
    async def latest_for_subject(session: AsyncSession, model_cls: Type, subject_field: str, subject_id: str):
        # Delegate to model if it implements a classmethod, else provide a generic query
        if hasattr(model_cls, "latest_for_subject"):
            return await model_cls.latest_for_subject(session, subject_id)

        stmt = select(model_cls).where(getattr(model_cls, subject_field) == subject_id).order_by(getattr(model_cls, "created_at").desc())
        result = await session.execute(stmt)
        return result.scalars().first()
