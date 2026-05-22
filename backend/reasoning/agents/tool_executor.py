"""
Tool Executor Agent.

Specialized agent that executes tools from the ToolRegistry.
Uses LLM-based parameter extraction to execute type-safe tools
based on the user's natural language request.
"""
import logging
import json
from typing import Dict, Any, Optional

from backend.core.config import get_settings
from backend.agent.tools.registry import ToolRegistry

settings = get_settings()
logger = logging.getLogger(__name__)


class ToolExecutorAgent:
    """Agent that extracts parameters for a tool and executes it."""

    def __init__(self):
        self.registry = ToolRegistry()
        self._client = None
        self._client_init_failed = False

    @property
    def client(self):
        if self._client is not None:
            return self._client
        if self._client_init_failed or not settings.groq_api_key:
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            return self._client
        except Exception as e:
            self._client_init_failed = True
            return None

    async def execute(self, query: str, tool_name: str) -> Dict[str, Any]:
        """Extract arguments using LLM and execute the tool."""
        logger.info(f"ToolExecutor executing tool '{tool_name}' for query: '{query}'")

        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {
                "answer": f"Error: Tool '{tool_name}' is not registered in the system.",
                "confidence": 0.0,
                "sources": []
            }

        # 1. Extract arguments from the natural language query using the tool schema
        schema = tool.args_schema.model_json_schema()
        
        if not self.client:
            return {
                "answer": f"Error: LLM client is offline. Cannot extract parameters for tool '{tool_name}'.",
                "confidence": 0.0,
                "sources": []
            }

        prompt = f"""You are a precise tool invocation agent. Extract the required parameters from the user's query for the tool: '{tool_name}'.

Tool Description: {tool.description}
Tool JSON Schema:
{json.dumps(schema, indent=2)}

User Query: "{query}"

Output ONLY a valid JSON object matching the parameters in the schema. Do not include markdown code block formatting. If a parameter is not found and has no default, estimate it or omit it.

Arguments JSON:"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You extract JSON arguments for tool calls. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=settings.groq_model,
                temperature=0,
            )
            
            content = response.choices[0].message.content.strip()
            # Clean possible markdown wrap
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            args = json.loads(content)
            logger.info(f"Extracted arguments for '{tool_name}': {args}")

            # 2. Execute the tool
            result = await self.registry.execute_tool(tool_name, **args)

            # 3. Format result nicely for user
            formatted_prompt = f"""Format the following raw output of the tool '{tool_name}' into a user-friendly, helpful response answering the user's query.

User Query: "{query}"
Raw Tool Output:
{json.dumps(result, indent=2) if not isinstance(result, str) else result}

Formatted Response:"""

            format_resp = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You format tool outputs into clean, natural language responses."},
                    {"role": "user", "content": formatted_prompt}
                ],
                model=settings.groq_model,
                temperature=0.3,
            )

            return {
                "answer": format_resp.choices[0].message.content,
                "confidence": 1.0,
                "sources": [f"tool_{tool_name}"]
            }

        except Exception as e:
            logger.error(f"ToolExecutor failed for tool '{tool_name}': {e}")
            return {
                "answer": f"Failed to execute action using '{tool_name}': {e}",
                "confidence": 0.0,
                "sources": []
            }
