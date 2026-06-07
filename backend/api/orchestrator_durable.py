from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from backend.core.database import async_session
from backend.models.reasoning_execution import ReasoningExecution

router = APIRouter()


class DurableStartRequest(BaseModel):
    query: str
    workspace_id: str
    user_id: Optional[str] = None


@router.post("/orchestrator/durable/start")
async def start_durable(req: DurableStartRequest, request: Request):
    if not req.query or not req.workspace_id:
        raise HTTPException(status_code=400, detail="query and workspace_id required")

    request_id = request.headers.get("X-Request-Id") or request.headers.get("x-request-id")

    # Persist a ReasoningExecution record
    exec = ReasoningExecution(
        workspace_id=req.workspace_id,
        query=req.query,
        status="running",
        state_snapshot={"query": req.query, "workspace_id": req.workspace_id},
        request_id=request_id,
    )

    async with async_session() as session:
        session.add(exec)
        await session.commit()
        await session.refresh(exec)

    return {"status": "created", "execution_id": exec.id}
