from typing import Dict, Any

from backend.agents.harness import TestHarness
from backend.agents.contracts import ToolProtocol, AgentProtocol


class MockIncrementTool:
    name = "increment"

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        value = int(inputs.get("value", 0))
        return {"result": "ok", "value": value + 1}


class SimpleAgent:
    def handle(self, inputs: Dict[str, Any], tools: Dict[str, ToolProtocol]) -> Dict[str, Any]:
        tool = tools.get("increment")
        if not tool:
            return {"error": "missing tool"}
        out = tool.run({"value": inputs.get("value", 0)})
        return {"agent_result": out}


def test_harness_runs_agent_with_tool():
    harness = TestHarness()
    harness.register_tool(MockIncrementTool())
    agent = SimpleAgent()
    res = harness.run_agent(agent, {"value": 2})
    assert res == {"agent_result": {"result": "ok", "value": 3}}
