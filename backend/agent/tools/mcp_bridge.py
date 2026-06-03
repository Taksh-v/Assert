from typing import Dict, Any
from pydantic import BaseModel, create_model, Field


class MCPBridge:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def _json_schema_to_pydantic(self, action_name: str, schema: Dict[str, Any]):
        # Create a pydantic model dynamically from a simple JSON schema dict
        safe_name = action_name.replace("-", "_")
        model_name = f"MCP_{safe_name}_Schema"

        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        fields = {}
        for prop, spec in properties.items():
            t = spec.get("type", "string")
            default = spec.get("default", ...)
            desc = spec.get("description")

            if t == "string":
                typ = (str,)
            elif t in ("integer", "number"):
                typ = (int,)
            elif t == "boolean":
                typ = (bool,)
            else:
                typ = (Any,)

            if prop in required and default is ...:
                fields[prop] = (typ[0], Field(..., description=desc))
            else:
                fields[prop] = (typ[0], Field(default, description=desc))

        Model = create_model(model_name, **fields)
        return Model
