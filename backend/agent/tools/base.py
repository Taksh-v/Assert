from typing import Any, Dict
import inspect
import asyncio
from pydantic import BaseModel, ValidationError, create_model


def _strip_titles(schema: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


class BaseTool:
    """Base class for tools used by agent tests.

    Subclasses must set `name`, `description`, and `args_schema` (a Pydantic model).
    """

    name: str = "base_tool"
    description: str = "Base tool"
    args_schema: BaseModel = None

    def get_tool_definition(self) -> Dict[str, Any]:
        # Build function definition using the args_schema JSON schema
        params = {}
        if self.args_schema is not None:
            try:
                schema = self.args_schema.model_json_schema()
            except Exception:
                schema = {}
            params = _strip_titles(schema)

        return {
            "type": "function",
            "function": {
                "name": getattr(self, "name", self.__class__.__name__),
                "description": getattr(self, "description", ""),
                "parameters": params,
            },
        }

    def _run(self, args: BaseModel) -> Any:  # pragma: no cover - to be implemented by subclasses
        raise NotImplementedError()

    async def execute(self, **kwargs) -> Any:
        # Validate inputs using pydantic model
        if self.args_schema is None:
            args_obj = None
        else:
            try:
                args_obj = self.args_schema(**kwargs)
            except ValidationError as e:
                raise ValueError(f"Invalid inputs for tool: {e}")

        # Call implementation, support sync or async _run
        if inspect.iscoroutinefunction(self._run):
            return await self._run(args_obj)
        else:
            # run in thread if blocking? keep simple and call directly
            result = self._run(args_obj)
            if asyncio.iscoroutine(result):
                return await result
            return result

    # Backwards-compatible sync wrapper
    def run_sync(self, **kwargs):
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self.execute(**kwargs))
