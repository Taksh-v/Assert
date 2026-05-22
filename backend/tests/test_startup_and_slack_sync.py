import pytest

from backend.core.config import get_settings
from backend.connectors import slack as slack_module
from backend.connectors.slack import SlackChannelPermissionError, SlackConnector


def test_slack_bot_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SLACK_BOT", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.enable_slack_bot is False


def test_slack_bot_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("ENABLE_SLACK_BOT", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.enable_slack_bot is True

    get_settings.cache_clear()


class FakeSlackClient:
    def __init__(self, channels):
        self.channels = channels
        self.history_channels = []

    def conversations_info(self, channel):
        return {"channel": self.channels[channel]}

    def conversations_history(self, channel, **kwargs):
        self.history_channels.append(channel)
        return {
            "messages": [
                {"user": "U1", "text": "A useful update", "ts": "1716300000.000000"}
            ],
            "response_metadata": {},
            "has_more": False,
        }


async def collect_async(iterator):
    items = []
    async for item in iterator:
        items.append(item)
    return items


@pytest.mark.asyncio
async def test_slack_sync_fetches_only_selected_channels(monkeypatch):
    def fake_get_messages(client, channel_id, since=None):
        response = client.conversations_history(channel_id)
        yield from response["messages"]

    monkeypatch.setattr(slack_module, "get_messages", fake_get_messages)

    client = FakeSlackClient(
        {
            "C_SELECTED": {"id": "C_SELECTED", "name": "selected", "is_member": True},
            "C_OTHER": {"id": "C_OTHER", "name": "other", "is_member": True},
        }
    )
    connector = SlackConnector()

    docs = await collect_async(
        connector.fetch_documents(client, selected_ids=["C_SELECTED"])
    )

    assert client.history_channels == ["C_SELECTED"]
    assert [doc.metadata["channel_id"] for doc in docs] == ["C_SELECTED"]


@pytest.mark.asyncio
async def test_slack_selected_non_member_channels_fail_actionably(monkeypatch):
    def fake_get_messages(client, channel_id, since=None):
        raise AssertionError("history should not be called for non-member channels")

    monkeypatch.setattr(slack_module, "get_messages", fake_get_messages)

    client = FakeSlackClient(
        {
            "C_PRIVATE": {"id": "C_PRIVATE", "name": "private", "is_member": False},
        }
    )
    connector = SlackConnector()

    with pytest.raises(SlackChannelPermissionError, match="Invite the Slack app"):
        await collect_async(connector.fetch_documents(client, selected_ids=["C_PRIVATE"]))
