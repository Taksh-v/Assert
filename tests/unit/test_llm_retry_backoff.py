import sys
import pathlib
import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from backend.core.llm_impl import SharedLLMClient


@pytest.mark.asyncio
async def test_retry_backoff(monkeypatch):
    calls = {"count": 0}

    async def flaky_acompletion(*args, **kwargs):
        calls["count"] += 1
        # fail twice then succeed
        if calls["count"] < 3:
            raise Exception("temporary network error")

        class Message:
            def __init__(self, content):
                self.content = content

        class Choice:
            def __init__(self, message):
                self.message = message

        class Resp:
            def __init__(self):
                self.choices = [Choice(Message("ok"))]

        return Resp()

    monkeypatch.setattr("backend.core.llm_impl.litellm.acompletion", flaky_acompletion)
    client = SharedLLMClient(model_type="smart")
    res = await client.chat_completion("s", "u")
    assert res == "ok"
