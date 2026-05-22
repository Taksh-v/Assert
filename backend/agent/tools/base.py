import abc
import logging
from typing import Any, Dict, Type
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

class BaseTool(abc.ABC):
    """
    Schema-Driven Type-Safe Tool Primitive.
    Inspired by Mastra.ai, uses Pydantic for strict input validation
    and automatic LLM tool definition generation.
    """
    
    name: str
    description: str
    args_schema: Type[BaseModel]

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Generate a OpenAI/Gemini/Claude compatible function tool definition.
        """
        schema = self.args_schema.model_json_schema()
        
        # Strip internal Pydantic titles from properties to keep schema clean for LLMs
        if "properties" in schema:
            for prop in schema["properties"].values():
                prop.pop("title", None)
        schema.pop("title", None)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        }

    def execute(self, **kwargs) -> Any:
        """
        Wrapper to validate input args against the schema before execution.
        """
        try:
            validated_args = self.args_schema.model_validate(kwargs)
            return self._run(validated_args)
        except ValidationError as e:
            logger.error(f"Validation failed for tool '{self.name}': {e}")
            raise ValueError(f"Invalid inputs for tool '{self.name}': {e.errors()}")

    async def execute_async(self, **kwargs) -> Any:
        """
        Wrapper to validate input args and execute asynchronously.
        Supports tools that override _run_async. Falls back to running _run in a thread.
        """
        try:
            validated_args = self.args_schema.model_validate(kwargs)
            if hasattr(self, "_run_async"):
                return await self._run_async(validated_args)
            
            # Check if _run is a coroutine function
            import inspect
            if inspect.iscoroutinefunction(self._run):
                return await self._run(validated_args)
            
            import asyncio
            return await asyncio.to_thread(self._run, validated_args)
        except ValidationError as e:
            logger.error(f"Validation failed for tool '{self.name}': {e}")
            raise ValueError(f"Invalid inputs for tool '{self.name}': {e.errors()}")

    @abc.abstractmethod
    def _run(self, args: Any) -> Any:
        """
        The actual execution logic of the tool (sync).
        """
        pass

    async def _run_async(self, args: Any) -> Any:
        """
        Optional async execution logic. Override this for async-native tools.
        """
        import asyncio
        return await asyncio.to_thread(self._run, args)
