import json
import os
from typing import Dict, Any

from jsonschema import validate, ValidationError

SKILLS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "skills.json")


def _ensure_data_dir():
    d = os.path.dirname(SKILLS_PATH)
    os.makedirs(d, exist_ok=True)


def load_registry() -> Dict[str, Any]:
    _ensure_data_dir()
    if not os.path.exists(SKILLS_PATH):
        return {}
    with open(SKILLS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(reg: Dict[str, Any]):
    _ensure_data_dir()
    with open(SKILLS_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2)


def register_skill_schema(name: str, input_schema: Dict[str, Any], output_schema: Dict[str, Any], metadata: Dict[str, Any] = None):
    reg = load_registry()
    reg[name] = {"input_schema": input_schema, "output_schema": output_schema, "metadata": metadata or {}}
    save_registry(reg)


def get_skill_schema(name: str):
    reg = load_registry()
    return reg.get(name)


def validate_skill_input(name: str, params: Dict[str, Any]):
    schema = get_skill_schema(name)
    if not schema:
        raise KeyError(f"Skill {name} not registered")
    try:
        validate(instance=params, schema=schema["input_schema"])
        return True
    except ValidationError as e:
        raise e
