import asyncio
from datetime import datetime
from backend.connectors.slack import SlackConnector, get_channels, get_messages

# Mocking the AsyncWebClient for Slack
class MockSlackClient:
    def __init__(self, token=None):
        self.token = token

    async def auth_test(self):
        return {"ok": True, "team": "Assest Mock Team"}

    async def conversations_list(self, **kwargs):
        # Return mock channels
        return {
            "channels": [
                {"id": "C12345", "name": "general", "num_members": 42, "purpose": {"value": "General discussion"}, "is_general": True},
                {"id": "C67890", "name": "engineering", "num_members": 10, "purpose": {"value": "Eng talk"}, "is_general": False}
            ],
            "response_metadata": {}
        }

    async def conversations_history(self, **kwargs):
        channel = kwargs.get("channel")
        if channel == "C12345":
            return {
                "messages": [
                    {"user": "U1", "text": "Hello world!", "ts": "1716300000.000000"},
                    {"user": "U2", "text": "Hi there!", "ts": "1716300100.000000"}
                ],
                "has_more": False,
                "response_metadata": {}
            }
        elif channel == "C67890":
            return {
                "messages": [
                    {"user": "U3", "text": "Deploying to prod.", "ts": "1716300200.000000"}
                ],
                "has_more": False,
                "response_metadata": {}
            }
        return {"messages": []}

async def test_dlt_slack_fetch():
    print("🚀 Initializing DLT Slack Connector with Mock Client...")
    
    # 1. Instantiate the connector
    connector = SlackConnector()
    
    # 2. Inject our mock client instead of real Slack connection
    mock_client = MockSlackClient(token="mock-token-123")
    
    print("\n--- Testing Resource Discovery ---")
    resources = await connector.list_resources(mock_client)
    for res in resources:
        print(f"Found Channel: {res['name']} (Members: {res['member_count']})")
        
    print("\n--- Testing Data Extraction & Normalization ---")
    doc_count = 0
    async for doc in connector.fetch_documents(mock_client, since=datetime.utcnow()):
        doc_count += 1
        print(f"\n📄 Document {doc_count}: {doc.title}")
        print(f"   Source ID: {doc.source_id}")
        print(f"   Metadata: {doc.metadata}")
        print(f"   Content Preview:\n{doc.raw_content}")

if __name__ == "__main__":
    asyncio.run(test_dlt_slack_fetch())