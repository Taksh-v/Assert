import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import get_db
from backend.models.user import User
from backend.api.users import get_current_user
from backend.api.connectors import verify_workspace_access
from backend.models.reasoning_execution import ReasoningExecution
from backend.reasoning.orchestrator import ReasoningOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reasoning", tags=["Reasoning"])

class StartReasoningRequest(BaseModel):
    query: str
    workspace_id: str
    max_iterations: Optional[int] = 5

class ResumeReasoningRequest(BaseModel):
    resume_data: Optional[Dict[str, Any]] = None
    user_input: Optional[str] = None  # Legacy string input

@router.post("/start")
async def start_reasoning(
    request: StartReasoningRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start a new durable reasoning execution for a query.
    Enforces workspace-level tenant isolation.
    """
    logger.info(f"Starting reasoning run for query: {request.query} on workspace: {request.workspace_id}")
    workspace_id = await verify_workspace_access(request.workspace_id, db, current_user)
    
    orchestrator = ReasoningOrchestrator()
    try:
        result = await orchestrator.run_durable(
            query=request.query,
            workspace_id=workspace_id,
            user_id=current_user.id,
            max_iterations=request.max_iterations
        )
        return result
    except Exception as e:
        logger.error(f"Error starting reasoning run: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{execution_id}")
async def get_reasoning_status(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve the current status and snapshot of a reasoning execution.
    """
    stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalars().first()
    
    if not execution:
        raise HTTPException(status_code=404, detail="Execution run not found")
        
    # Enforce workspace access
    await verify_workspace_access(execution.workspace_id, db, current_user)
    
    return {
        "execution_id": execution.id,
        "workspace_id": execution.workspace_id,
        "query": execution.query,
        "status": execution.status,
        "current_task_index": execution.current_task_index,
        "suspend_schema": execution.state_snapshot.get("suspend_schema"),
        "state_snapshot": execution.state_snapshot,
        "created_at": execution.created_at.isoformat(),
        "updated_at": execution.updated_at.isoformat()
    }

@router.post("/resume/{execution_id}")
async def resume_reasoning(
    execution_id: str,
    request: ResumeReasoningRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Resume a suspended reasoning execution by providing user input or approval.
    """
    logger.info(f"Resuming reasoning run: {execution_id}")
    
    # 1. Fetch execution
    stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalars().first()
    
    if not execution:
        raise HTTPException(status_code=404, detail="Execution run not found")
        
    # Enforce workspace access
    await verify_workspace_access(execution.workspace_id, db, current_user)
    
    if execution.status != "suspended":
        raise HTTPException(status_code=400, detail=f"Execution is not in suspended state (current: {execution.status})")
        
    orchestrator = ReasoningOrchestrator()
    try:
        result = await orchestrator.run_durable(
            query=execution.query,
            workspace_id=execution.workspace_id,
            execution_id=execution_id,
            user_input=__import__('json').dumps(request.resume_data) if request.resume_data else request.user_input,
            user_id=current_user.id
        )
        return result
    except Exception as e:
        logger.error(f"Error resuming reasoning run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Eval Scores Endpoint ──────────────────────────────────
@router.get("/scores/{execution_id}")
async def get_eval_scores(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve quality evaluation scores for a specific reasoning execution.
    Returns faithfulness, relevancy, hallucination, and completeness scores.
    """
    # Verify execution exists and user has access
    stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalars().first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution run not found")

    await verify_workspace_access(execution.workspace_id, db, current_user)

    from backend.evals.pipeline import ScoringPipeline
    pipeline = ScoringPipeline()
    scores = await pipeline.get_scores(execution_id)

    return {
        "execution_id": execution_id,
        "scores": scores
    }


# ── Memory Reflection Endpoint ────────────────────────────
class ReflectRequest(BaseModel):
    workspace_id: str

@router.post("/memory/reflect")
async def trigger_memory_reflection(
    request: ReflectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a Reflector cycle to maintain the observation memory log.
    Decays old observations, merges duplicates, and prunes low-priority entries.
    """
    workspace_id = await verify_workspace_access(request.workspace_id, db, current_user)

    from backend.memory.manager import MemoryManager
    manager = MemoryManager()
    summary = await manager.trigger_reflection(workspace_id, user_id=current_user.id)

    return {
        "workspace_id": workspace_id,
        "reflection_summary": summary
    }

