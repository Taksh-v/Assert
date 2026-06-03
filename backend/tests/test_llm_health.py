from types import SimpleNamespace
import pytest
from backend.core.llm_impl import LLMHealthReport, build_llm_health_report

@pytest.mark.asyncio
async def test_build_llm_health_report_warns_when_openrouter_model_missing_key(monkeypatch):
    fake_settings = SimpleNamespace(
        app_secret_key="super-secret-value",
        openrouter_api_key=None,
        groq_api_key=None,
        litellm_proxy_url="http://localhost:4000",
        openrouter_smart_model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
        openrouter_fast_model="openrouter/google/gemini-2.0-flash-lite:free",
        openrouter_fallback_models="openrouter/z-ai/glm-4.5-air:free",
        groq_model="groq/llama-3.3-70b-versatile",
        company_brain_fast_model="openai/company-brain-fast",
        strict_model_validation=False,
        perform_llm_ping=False,
        active_ping_on_startup=False,
        langfuse_public_key="pk-lf-public",
        langfuse_secret_key="sk-lf-secret",
        slack_signing_secret="assest_slack_secret"
    )

    monkeypatch.setattr("backend.core.llm_impl.settings", fake_settings)

    report = await build_llm_health_report()

    assert report.provider == "proxy"
    assert report.model == "openai/company-brain-fast"
    assert report.fallback_models == []
    assert "openrouter_smart_model configured but openrouter_api_key missing" in report.warnings

@pytest.mark.asyncio
async def test_llm_health_endpoint_returns_report_payload(monkeypatch):
    from backend.api import llm as llm_api

    fake_report = LLMHealthReport(
        provider="openrouter",
        model="openrouter/google/gemini-2.0-flash-lite:free",
        fallback_models=["openrouter/z-ai/glm-4.5-air:free"],
        warnings=["example warning"],
        strict_validation_enabled=True,
        active_check={"status": "success", "latency_ms": 100}
    )

    async def mock_report(perform_ping=False):
        return fake_report

    monkeypatch.setattr(llm_api, "build_llm_health_report", mock_report)

    result = await llm_api.llm_health()

    assert result == {
        "provider": "openrouter",
        "model": "openrouter/google/gemini-2.0-flash-lite:free",
        "fallbacks": ["openrouter/z-ai/glm-4.5-air:free"],
        "strict_validation_enabled": True,
        "warnings": ["example warning"],
        "active_check": {"status": "success", "latency_ms": 100}
    }

@pytest.mark.asyncio
async def test_llm_ping_functionality(monkeypatch):
    from backend.core.llm_impl import SharedLLMClient
    
    # Mock litellm.acompletion to avoid real network calls
    async def mock_acompletion(*args, **kwargs):
        class MockResp:
            def __init__(self):
                self.choices = [SimpleNamespace(message=SimpleNamespace(content="pong"))]
        return MockResp()
        
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    
    client = SharedLLMClient()
    result = await client.ping()
    
    assert result["status"] == "success"
    assert "latency_ms" in result
    assert "model" in result
