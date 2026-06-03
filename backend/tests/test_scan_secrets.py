from pathlib import Path

from scripts.scan_secrets import scan_file


def test_scan_file_flags_secret_like_assignments(tmp_path):
    sample = tmp_path / ".env"
    sample.write_text("API_KEY=abc123\nNORMAL=value\n", encoding="utf-8")

    findings = scan_file(sample)

    assert findings
    assert any("potential secret-like value" in item for item in findings)


def test_scan_file_passes_clean_file(tmp_path):
    sample = tmp_path / ".env.example"
    sample.write_text("APP_ENV=development\nFEATURE_FLAG=true\n", encoding="utf-8")

    findings = scan_file(sample)

    assert findings == []
