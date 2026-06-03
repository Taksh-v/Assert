import os
import json
from backend.connectors.skill_registry_service import register_skill_schema, get_skill_schema, validate_skill_input, SKILLS_PATH


def test_register_and_validate_skill(tmp_path, monkeypatch):
    # Use a temp SKILLS_PATH to avoid touching repo data
    tmp_file = tmp_path / "skills.json"
    monkeypatch.setattr('backend.connectors.skill_registry_service.SKILLS_PATH', str(tmp_file))

    name = "test.skill"
    input_schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    output_schema = {"type": "object"}

    register_skill_schema(name, input_schema, output_schema, metadata={"idempotent": True})
    s = get_skill_schema(name)
    assert s is not None
    # Validate good input
    assert validate_skill_input(name, {"x": 1}) is True

    # Invalid input raises
    try:
        validate_skill_input(name, {"x": "nope"})
        assert False, "Validation should fail"
    except Exception:
        pass
