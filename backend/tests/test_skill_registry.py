from backend.connectors.skill_registry import get_skill, list_skills
import importlib


def test_google_drive_skill_registered():
    # import the registration module to ensure registration runs
    importlib.import_module('backend.connectors.register_google_drive_skill')
    skills = list_skills()
    assert 'google_drive.list' in skills
    s = get_skill('google_drive.list')
    assert s is not None
    assert 'input_schema' in s and 'output_schema' in s
