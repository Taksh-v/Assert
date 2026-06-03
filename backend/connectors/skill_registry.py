from typing import Dict, Any

_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_skill(name: str, input_schema: Dict[str, Any], output_schema: Dict[str, Any], metadata: Dict[str, Any] = None):
    _REGISTRY[name] = {
        "input_schema": input_schema,
        "output_schema": output_schema,
        "metadata": metadata or {}
    }


def get_skill(name: str):
    return _REGISTRY.get(name)


def list_skills():
    return list(_REGISTRY.keys())
