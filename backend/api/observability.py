import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.connectors import verify_workspace_access
from backend.api.users import get_current_user
from backend.core.database import get_db
from backend.models.query_log import QueryLog
from backend.models.reasoning_execution import ReasoningExecution
from backend.models.user import User

router = APIRouter(prefix="/observability", tags=["Observability"])


class TraceItem(BaseModel):
    id: str
    question: str
    answer_preview: Optional[str] = None
    request_id: Optional[str] = None
    created_at: datetime
    response_time_ms: Optional[int] = None
    faithfulness_score: Optional[float] = None
    relevance_score: Optional[float] = None
    eval_reasoning: Optional[str] = None
    sources_count: int = 0


class ReasoningRunItem(BaseModel):
    execution_id: str
    query: str
    status: str
    request_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    confidence: float = 0.0
    eval_count: int = 0
    flagged_for_review: bool = False
    iterations: int = 0


class ObservabilityOverview(BaseModel):
    workspace_id: str
    query_count: int
    avg_response_time_ms: float = 0.0
    avg_faithfulness: float = 0.0
    avg_relevance: float = 0.0
    low_confidence_count: int = 0
    recent_queries: List[TraceItem]
    recent_reasoning_runs: List[ReasoningRunItem]


def _normalize_score(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@router.get("/overview", response_model=ObservabilityOverview)
async def get_observability_overview(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a compact observability snapshot for the active workspace.
    Intended for the admin console: recent traces, evals, and durable reasoning runs.
    """
    resolved_workspace_id = await verify_workspace_access(workspace_id, db, current_user)

    query_count_stmt = select(func.count(QueryLog.id)).where(QueryLog.workspace_id == resolved_workspace_id)
    avg_stmt = select(
        func.coalesce(func.avg(QueryLog.response_time_ms), 0),
        func.coalesce(func.avg(QueryLog.faithfulness_score), 0),
        func.coalesce(func.avg(QueryLog.relevance_score), 0),
        func.count(QueryLog.id),
    ).where(QueryLog.workspace_id == resolved_workspace_id)

    recent_query_stmt = (
        select(QueryLog)
        .where(QueryLog.workspace_id == resolved_workspace_id)
        .order_by(desc(QueryLog.created_at))
        .limit(10)
    )

    recent_reasoning_stmt = (
        select(ReasoningExecution)
        .where(ReasoningExecution.workspace_id == resolved_workspace_id)
        .order_by(desc(ReasoningExecution.created_at))
        .limit(8)
    )

    query_count = (await db.execute(query_count_stmt)).scalar() or 0
    avg_row = (await db.execute(avg_stmt)).one()
    recent_queries = (await db.execute(recent_query_stmt)).scalars().all()
    recent_reasoning = (await db.execute(recent_reasoning_stmt)).scalars().all()

    recent_query_items: List[TraceItem] = []
    low_confidence_count = 0
    for item in recent_queries:
        score = _normalize_score(item.faithfulness_score)
        if score and score < 0.5:
            low_confidence_count += 1
        recent_query_items.append(
            TraceItem(
                id=item.id,
                question=item.question,
                answer_preview=(item.answer or "")[:180] or None,
                request_id=item.request_id,
                created_at=item.created_at,
                response_time_ms=item.response_time_ms,
                faithfulness_score=item.faithfulness_score,
                relevance_score=item.relevance_score,
                eval_reasoning=item.eval_reasoning,
                sources_count=len(item.sources or []),
            )
        )

    recent_reasoning_items: List[ReasoningRunItem] = []
    for run in recent_reasoning:
        state_snapshot: Dict[str, Any] = run.state_snapshot or {}
        eval_scores = state_snapshot.get("eval_scores") or []
        if isinstance(eval_scores, str):
            try:
                eval_scores = json.loads(eval_scores)
            except Exception:
                eval_scores = []

        score_values = [
            float(score.get("score", 0.0))
            for score in eval_scores
            if isinstance(score, dict) and score.get("score") is not None
        ]
        confidence = float(state_snapshot.get("confidence_score") or 0.0)
        recent_reasoning_items.append(
            ReasoningRunItem(
                execution_id=run.id,
                query=run.query,
                status=run.status,
                request_id=run.request_id,
                created_at=run.created_at,
                updated_at=run.updated_at,
                confidence=confidence,
                eval_count=len(score_values),
                flagged_for_review=bool(state_snapshot.get("flagged_for_review", False)),
                iterations=int(state_snapshot.get("iterations", run.current_task_index or 0) or 0),
            )
        )

    return ObservabilityOverview(
        workspace_id=resolved_workspace_id,
        query_count=int(query_count),
        avg_response_time_ms=float(avg_row[0] or 0),
        avg_faithfulness=float(avg_row[1] or 0),
        avg_relevance=float(avg_row[2] or 0),
        low_confidence_count=low_confidence_count,
        recent_queries=recent_query_items,
        recent_reasoning_runs=recent_reasoning_items,
    )
