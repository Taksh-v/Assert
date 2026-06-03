import asyncio
import sys
import pathlib
import pytest

# Ensure repo root is on sys.path when running tests
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from backend.core.llm_impl import SharedLLMClient


@pytest.mark.asyncio
async def test_async_fallback(monkeypatch):
    calls = {"count": 0}

    async def fake_acompletion(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise Exception("No endpoints found for model")
        # emulate litellm response structure
        class Message:
            def __init__(self, content):
                self.content = content

        class Choice:
            def __init__(self, message):
                self.message = message

        class Resp:
            def __init__(self):
                self.choices = [Choice(Message("fallback answer"))]

        return Resp()

    # Patch the litellm acall used inside llm_impl
    monkeypatch.setattr("backend.core.llm_impl.litellm.acompletion", fake_acompletion)

    client = SharedLLMClient(model_type="smart")
    res = await client.chat_completion("system", "user")
    assert res == "fallback answer"
