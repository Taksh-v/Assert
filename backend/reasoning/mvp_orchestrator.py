import logging
from typing import Dict, Any, Callable, List
from backend.observability.telemetry import tracer

logger = logging.getLogger(__name__)


class Planner:
    """Simple planner that turns a user intent into agent tasks.

    This is intentionally minimal for an MVP; later it will produce
    structured plans with subtasks, goals, and priorities.
    """

    def plan(self, user_intent: str) -> List[Dict[str, Any]]:
        # For MVP return two tasks targeting agent_a and agent_b.
        with tracer.start_as_current_span("orchestrator.plan") as span:
            span.set_attribute("user_intent", user_intent)
            return [
                {"agent": "agent_a", "input": user_intent},
                {"agent": "agent_b", "input": user_intent},
            ]


class Dispatcher:
    """Dispatches planned tasks to registered agent handlers."""

    def __init__(self, agents: Dict[str, Callable[[Any], Any]]):
        self.agents = agents

    def dispatch(self, task: Dict[str, Any]) -> Any:
        agent_name = task["agent"]
        with tracer.start_as_current_span("orchestrator.dispatch") as span:
            span.set_attribute("agent", agent_name)
            if agent_name not in self.agents:
                raise KeyError(f"Unknown agent {agent_name}")
            handler = self.agents[agent_name]
            return handler(task["input"])


class Orchestrator:
    """Coordinates planning and dispatch, returns aggregated results."""

    def __init__(self, planner: Planner, dispatcher: Dispatcher):
        self.planner = planner
        self.dispatcher = dispatcher

    def orchestrate(self, user_intent: str) -> Dict[str, Any]:
        tasks = self.planner.plan(user_intent)
        results: Dict[str, Any] = {}
        for t in tasks:
            try:
                res = self.dispatcher.dispatch(t)
                results.setdefault(t["agent"], []).append(res)
            except Exception as e:
                logger.exception("Agent task failed")
                results.setdefault(t["agent"], []).append({"error": str(e)})
        return results


__all__ = ["Planner", "Dispatcher", "Orchestrator"]
