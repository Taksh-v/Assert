import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000/api"
TOKEN = "your_notion_token_here"

async def test_notion_sync():
    async with httpx.AsyncClient() as client:
        # 1. Get default workspace
        print("🔍 Getting default workspace...")
        resp = await client.get(f"{BASE_URL}/workspaces/default")
        workspace = resp.json()
        workspace_id = workspace["id"]
        print(f"✅ Using Workspace: {workspace_id}")

        # 2. Check if connector already exists
        print("🔍 Checking existing connectors...")
        resp = await client.get(f"{BASE_URL}/connectors", params={"workspace_id": workspace_id})
        connectors = resp.json()
        notion_conn = next((c for c in connectors if c["type"] == "notion"), None)

        if not notion_conn:
            print("🆕 Creating Notion connector...")
            resp = await client.post(f"{BASE_URL}/connectors", json={
                "workspace_id": workspace_id,
                "type": "notion",
                "config": {"token": TOKEN}
            })
            if resp.status_code != 200:
                print(f"❌ Failed to create connector: {resp.text}")
                return
            notion_conn = resp.json()
            print(f"✅ Created Connector: {notion_conn['id']}")
        else:
            print(f"✅ Found existing Notion connector: {notion_conn['id']}")

        # 3. Test Connection
        print("🔌 Testing connection...")
        resp = await client.post(f"{BASE_URL}/connectors/{notion_conn['id']}/test")
        print(f"📊 Test Result: {json.dumps(resp.json(), indent=2)}")

        # 4. Trigger Sync
        print("🚀 Triggering Sync...")
        resp = await client.post(f"{BASE_URL}/connectors/{notion_conn['id']}/sync")
        print(f"📊 Sync Result: {json.dumps(resp.json(), indent=2)}")
        
        print("\n💡 Check the backend terminal logs to see the ingestion progress!")

if __name__ == "__main__":
    asyncio.run(test_notion_sync())
