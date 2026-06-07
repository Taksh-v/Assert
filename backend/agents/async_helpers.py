import asyncio
from typing import Dict, Any
from backend.agents.contracts import ToolProtocol

async def run_tool_async(tool: ToolProtocol, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Runs a tool's run method asynchronously in the default thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, tool.run, inputs)
