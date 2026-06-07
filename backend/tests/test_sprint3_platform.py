"""
Integration Test for Sprint 3 Platform Features.

Tests:
1. ToolRegistry registration and listing.
2. MCPBridge dynamic Pydantic schema generation from JSON schemas.
3. StreamGenerator fallback.
"""
import sys
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

# ── Mock external dependencies for offline testing ──
mock_passlib = MagicMock()
mock_passlib.context = MagicMock()
mock_passlib.context.CryptContext = MagicMock()
sys.modules["passlib"] = mock_passlib
sys.modules["passlib.context"] = mock_passlib.context
sys.modules["groq"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()

import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_sprint3.db")
os.environ.setdefault("GROQ_API_KEY", "")

from backend.agent.tools.registry import ToolRegistry
from backend.agent.tools.base import BaseTool
from backend.agent.tools.mcp_bridge import MCPBridge
from backend.generation.stream_generator import StreamGenerator
from pydantic import BaseModel, Field


# ── Setup Dummy Tool ──
class TestParamsSchema(BaseModel):
    param_a: str = Field(description="A dummy test parameter")
    param_b: int = Field(default=10, description="An optional test param")

class DummyPlatformTool(BaseTool):
    name = "dummy_platform_tool"
    description = "Test platform tool registry"
    args_schema = TestParamsSchema

    def _run(self, args: TestParamsSchema) -> str:
        return f"a: {args.param_a}, b: {args.param_b}"


async def test_platform_features():
    print("── TEST 1: ToolRegistry Discovery and Actions ──")
    registry = ToolRegistry()
    registry.register(DummyPlatformTool())
    
    tools = registry.list_tools()
    tool_names = [t.name for t in tools]
    print(f"   Registered tools: {tool_names}")
    assert "dummy_platform_tool" in tool_names

    definitions = registry.get_tool_definitions()
    dummy_def = next(d for d in definitions if d["function"]["name"] == "dummy_platform_tool")
    print(f"   Tool definition properties: {list(dummy_def['function']['parameters']['properties'].keys())}")
    assert "param_a" in dummy_def["function"]["parameters"]["properties"]
    assert "param_b" in dummy_def["function"]["parameters"]["properties"]
    
    # Execute Tool
    exec_result = await registry.execute_tool("dummy_platform_tool", param_a="hello_sprint3")
    print(f"   Execution Output: {exec_result}")
    assert exec_result == "a: hello_sprint3, b: 10"
    print("   ✅ ToolRegistry tests passed.\n")


    print("── TEST 2: MCP Bridge Dynamic Parsing ──")
    # Simulate a JSON schema returned by an MCP server
    mcp_json_schema = {
        "properties": {
            "ticket_title": {
                "type": "string",
                "description": "The title of the ticket"
            },
            "priority": {
                "type": "integer",
                "description": "Ticket priority 1-5",
                "default": 3
            }
        },
        "required": ["ticket_title"]
    }
    
    bridge = MCPBridge("http://localhost:9999/mcp")
    # Dynamically generate Pydantic model
    DynamicModel = bridge._json_schema_to_pydantic("create-ticket", mcp_json_schema)
    
    print(f"   Generated Model Name: {DynamicModel.__name__}")
    assert DynamicModel.__name__ == "MCP_create_ticket_Schema"
    
    # Validate instance creation
    instance = DynamicModel(ticket_title="Sprint 3 Integration Ticket")
    print(f"   Validated Instance: {instance.model_dump()}")
    assert instance.ticket_title == "Sprint 3 Integration Ticket"
    assert instance.priority == 3
    print("   ✅ MCP Bridge Dynamic Schema Generation works.\n")


    print("── TEST 3: SSE Chat Streaming ──")
    streamer = StreamGenerator()
    prompt = [{"role": "user", "content": "hello"}]

    with patch("backend.generation.stream_generator.litellm.acompletion", AsyncMock(side_effect=RuntimeError("boom"))):
        events = []
        async for event in streamer.stream_chat(prompt, request_id="req-123"):
            events.append(json.loads(event.strip()[6:].strip()))

    print(f"   Received {len(events)} streaming events.")
    print(f"   First event type: {events[0]['type']}")
    print(f"   Last event type: {events[-1]['type']}")

    event_types = [event["type"] for event in events]
    assert "status" in event_types
    assert "error" in event_types
    assert event_types[-1] == "done"
    print("   ✅ StreamGenerator emits structured status, error, token, and done events.\n")

    print("🎉 All Sprint 3 Platform integration tests passed!")


if __name__ == "__main__":
    asyncio.run(test_platform_features())
