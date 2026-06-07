from typing import Dict, Any
from backend.agents.contracts import ToolProtocol

class TestHarness:
    """
    TestHarness acts as the runtime container for agents and their tools.
    Allows registering tools and executing agent logic in test environments.
    """
    __test__ = False

    def __init__(self):
        self.tools: Dict[str, ToolProtocol] = {}

    def register_tool(self, tool: ToolProtocol) -> None:
        self.tools[tool.name] = tool

    def run_agent(self, agent: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return agent.handle(inputs, self.tools)

    async def run_agent_async(self, agent: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return await agent.handle(inputs, self.tools)
