import time
import asyncio

from backend.agents.harness import TestHarness
from backend.agents.async_helpers import run_tool_async


class BlockingTool:
    name = "blocker"

    def run(self, inputs):
        # simulate blocking work
        time.sleep(0.05)
        return {"value": int(inputs.get("value", 0)) + 10}


class AsyncAgent:
    async def handle(self, inputs, tools):
        tool = tools.get("blocker")
        if not tool:
            return {"error": "missing"}
        out = await run_tool_async(tool, {"value": inputs.get("value", 0)})
        return {"agent_result": out}


async def test_async_harness_runs_blocking_tool():
    harness = TestHarness()
    harness.register_tool(BlockingTool())
    agent = AsyncAgent()
    res = await harness.run_agent_async(agent, {"value": 1})
    assert res == {"agent_result": {"value": 11}}
