import asyncio
from typing import Dict, List, Any


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Any] = {}

    def register(self, tool: Any) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> List[Any]:
        return list(self._tools.values())

    def get_tool(self, name: str):
        return self._tools.get(name)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [t.get_tool_definition() for t in self._tools.values()]

    async def execute_tool(self, name: str, **kwargs) -> Any:
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool {name} not registered")

        result = tool.execute(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result
