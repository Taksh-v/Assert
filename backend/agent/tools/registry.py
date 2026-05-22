"""
Universal Tool Registry.

Manages registration, discovery, and serialization of all tools
available to the agents. Supports both local schema-driven tools and
dynamic MCP (Model Context Protocol) bridged tools.
"""
import logging
from typing import Dict, Any, List, Optional
from backend.agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

class ToolRegistry:
    """
    Registry for tools that agents can use.
    Provides methods to list definitions and execute tools by name.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ToolRegistry, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.tools: Dict[str, BaseTool] = {}
        self._load_builtin_tools()
        self._initialized = True

    def _load_builtin_tools(self):
        """Automatically load built-in tools."""
        try:
            from backend.core.config import get_settings
            settings = get_settings()
            
            # Load GitHub tools if token is available
            github_token = getattr(settings, "github_token", None) or getattr(settings, "github_api_key", None)
            if github_token:
                from backend.agent.tools.github import GetRepoIssuesTool, GetLatestCommitsTool
                self.register(GetRepoIssuesTool(github_token))
                self.register(GetLatestCommitsTool(github_token))
                logger.info("GitHub tools registered in ToolRegistry.")
        except Exception as e:
            logger.warning(f"Failed to auto-load builtin tools: {e}")

    def register(self, tool: BaseTool) -> None:
        """Register a new tool."""
        if tool.name in self.tools:
            logger.info(f"Overwriting tool '{tool.name}' in registry.")
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieve a tool by name."""
        return self.tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self.tools.values())

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get LLM-compliant definitions for all registered tools."""
        return [tool.get_tool_definition() for tool in self.tools.values()]

    async def execute_tool(self, name: str, **kwargs) -> Any:
        """Execute a tool by name asynchronously."""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry.")
        return await tool.execute_async(**kwargs)
