"""
Model Context Protocol (MCP) Client Bridge.

Allows the Assest Agentic Engine to dynamically discover and connect to external
MCP servers. Translates remote MCP tools into type-safe local BaseTool instances at runtime.
"""
import logging
import httpx
from typing import Dict, Any, List, Type
from pydantic import BaseModel, create_model, Field
from backend.agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

class MCPRemoteTool(BaseTool):
    """
    Dynamically instantiated BaseTool representing a remote MCP tool.
    """
    def __init__(self, name: str, description: str, args_schema: Type[BaseModel], endpoint_url: str):
        self.name = name
        self.description = description
        self.args_schema = args_schema
        self.endpoint_url = endpoint_url

    def _run(self, args: Any) -> Any:
        # Since MCP tools run over HTTP/network, run synchronously by wrapping the async call.
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._run_async(args))

    async def _run_async(self, args: BaseModel) -> Any:
        """Call the remote MCP server to execute this tool."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": self.name,
                "arguments": args.model_dump()
            },
            "id": 1
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.endpoint_url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    raise ValueError(f"Remote MCP error: {data['error']}")
                
                result = data.get("result", {})
                # MCP tools typically return {"content": [{"type": "text", "text": "..."}]}
                content = result.get("content", [])
                if content and isinstance(content, list):
                    text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    if text_parts:
                        return "\n".join(text_parts)
                return result
        except Exception as e:
            logger.error(f"Failed to execute remote MCP tool '{self.name}': {e}")
            raise RuntimeError(f"MCP execution failed: {e}")


class MCPBridge:
    """
    Bridge client to interact with external MCP servers over HTTP/JSON-RPC.
    """
    def __init__(self, server_url: str):
        """
        :param server_url: The JSON-RPC endpoint of the MCP server (e.g., http://localhost:8000/mcp)
        """
        self.server_url = server_url

    async def discover_tools(self) -> List[BaseTool]:
        """
        Query the remote MCP server for tools and construct BaseTool instances.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.server_url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    logger.error(f"MCP listTools returned error: {data['error']}")
                    return []
                
                result = data.get("result", {})
                tools_list = result.get("tools", [])
                
                discovered = []
                for t in tools_list:
                    name = t.get("name")
                    desc = t.get("description", "")
                    input_schema = t.get("inputSchema", {})
                    
                    # Create dynamic Pydantic model for validation
                    pydantic_schema = self._json_schema_to_pydantic(name, input_schema)
                    
                    remote_tool = MCPRemoteTool(
                        name=name,
                        description=desc,
                        args_schema=pydantic_schema,
                        endpoint_url=self.server_url
                    )
                    discovered.append(remote_tool)
                    logger.info(f"Discovered remote MCP tool: {name}")
                
                return discovered
        except Exception as e:
            logger.error(f"Failed to discover tools from MCP server at {self.server_url}: {e}")
            return []

    def _json_schema_to_pydantic(self, name: str, schema: Dict[str, Any]) -> Type[BaseModel]:
        """
        Dynamically convert a JSON schema representation into a Pydantic model class.
        """
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        fields = {}
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        
        for prop_name, prop_def in properties.items():
            prop_type_str = prop_def.get("type", "string")
            prop_type = type_mapping.get(prop_type_str, Any)
            prop_desc = prop_def.get("description", "")
            
            if prop_name in required:
                fields[prop_name] = (prop_type, Field(..., description=prop_desc))
            else:
                default_val = prop_def.get("default", None)
                fields[prop_name] = (prop_type, Field(default=default_val, description=prop_desc))
        
        # Fallback if no properties defined
        if not fields:
            fields["input"] = (str, Field(default="", description="Default string input"))
            
        model_name = f"MCP_{name.replace('-', '_')}_Schema"
        return create_model(model_name, **fields)
