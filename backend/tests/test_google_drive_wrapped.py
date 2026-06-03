import pytest

from backend.connectors.wrappers.google_drive_wrapped import list_resources_wrapped


class FakeConnector:
    def __init__(self):
        self.disconnected = False

    async def connect(self, config):
        return {"config": config}

    async def list_resources(self, connection):
        return [{"id": "1", "name": "Doc A", "type": "file"}]

    async def disconnect(self, connection):
        self.disconnected = True


@pytest.mark.asyncio
async def test_google_drive_wrapper_lists_resources(monkeypatch):
    fake = FakeConnector()

    import backend.connectors.wrappers.google_drive_wrapped as mod
    monkeypatch.setattr(mod, "GoogleDriveConnector", lambda: fake)

    result = await list_resources_wrapped({"access_token": "dummy"})

    assert result["status"] == "ok"
    assert result["resources"] == [{"id": "1", "name": "Doc A", "type": "file"}]
    assert fake.disconnected is True
