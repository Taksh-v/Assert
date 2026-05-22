"""
Tools REST API endpoints.

Allows listing all registered tools and connecting to external MCP servers.
"""
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.users import get_current_user
from backend.models.user import User
from backend.agent.tools.registry import ToolRegistry
from backend.agent.tools.mcp_bridge import MCPBridge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools", tags=["Tools"])

class RegisterMCPServerRequest(BaseModel):
    server_url: str = Field(description="The HTTP base URL of the JSON-RPC MCP server")

class ToolResponse(BaseModel):
    name: str
    description: str
    definition: Dict[str, Any]

@router.get("", response_model=List[ToolResponse])
async def list_tools(current_user: User = Depends(get_current_user)):
    """List all registered tools and their schemas."""
    registry = ToolRegistry()
    tools = registry.list_tools()
    
    return [
        ToolResponse(
            name=t.name,
            description=t.description,
            definition=t.get_tool_definition()
        )
        for t in tools
    ]

@router.post("/register-mcp")
async def register_mcp_server(
    request: RegisterMCPServerRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Connect to an external MCP server, discover its tools,
    and register them in the ToolRegistry.
    """
    logger.info(f"Registering MCP server: {request.server_url}")
    bridge = MCPBridge(request.server_url)
    
    discovered_tools = await bridge.discover_tools()
    if not discovered_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Could not discover any tools from the MCP server at {request.server_url}. Verify it is running and accessible."
        )
        
    registry = ToolRegistry()
    registered_names = []
    for tool in discovered_tools:
        registry.register(tool)
        registered_names.append(tool.name)
        
    return {
        "status": "success",
        "message": f"Successfully registered {len(discovered_tools)} tools from MCP server",
        "registered_tools": registered_names
    }
