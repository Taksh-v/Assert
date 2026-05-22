import asyncio
from backend.connectors.slack import SlackConnector
from datetime import datetime
from slack_sdk.web.async_client import AsyncWebClient

async def test_slack():
    conn = SlackConnector()
    client = AsyncWebClient(token="xoxb-invalid-token")
        
    print("Testing DLT resource listing generator...")
    try:
        resources = await conn.list_resources(client)
        print("Resources:", resources)
    except Exception as e:
        print("List resources failed:", e)

    print("Testing DLT fetch_documents generator...")
    try:
        async for doc in conn.fetch_documents(client, since=datetime.now()):
            print(doc.title)
    except Exception as e:
        print("Fetch documents failed:", e)

if __name__ == "__main__":
    asyncio.run(test_slack())
