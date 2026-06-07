from backend.connectors.google_drive import GoogleDriveConnector
from backend.connectors.wrappers.skill_wrapper import skill_wrapper


@skill_wrapper("google_drive.list", idempotent=False)
async def list_resources_wrapped(connector_config: dict, idempotency_key: str = None):
    """Async skill adapter for Google Drive discovery.

    This instantiates the connector, connects using the provided config,
    fetches resources, and disconnects when finished.
    """
    connector = GoogleDriveConnector()
    connection = await connector.connect(connector_config)
    try:
        resources = await connector.list_resources(connection)
        return {"status": "ok", "resources": resources}
    finally:
        await connector.disconnect(connection)
