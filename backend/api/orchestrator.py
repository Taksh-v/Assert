from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.reasoning.mvp_orchestrator import Planner, Dispatcher, Orchestrator
from backend.observability.telemetry import tracer

router = APIRouter()


class OrchestratorRequest(BaseModel):
    intent: str


@router.post("/orchestrator/run")
async def run_orchestrator(req: OrchestratorRequest, request: Request):
    if not req.intent:
        raise HTTPException(status_code=400, detail="intent is required")

    # Simple in-process agents for MVP
    class AgentA:
        def __call__(self, inp):
            return {"result": f"agent_a processed: {inp}"}

    class AgentB:
        def __call__(self, inp):
            return {"result": f"agent_b processed: {inp}"}

    planner = Planner()
    dispatcher = Dispatcher({"agent_a": AgentA(), "agent_b": AgentB()})
    orch = Orchestrator(planner, dispatcher)

    # Propagate request-id if present
    request_id = request.headers.get("X-Request-Id") or request.headers.get("x-request-id")

    # Trace the orchestration request
    with tracer.start_as_current_span("orchestrator.request") as span:
        span.set_attribute("intent", req.intent)
        if request_id:
            span.set_attribute("request_id", request_id)
        results = orch.orchestrate(req.intent)
        span.set_attribute("agents.count", len(results))

    return {"status": "ok", "results": results}
