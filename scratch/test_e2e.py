import asyncio
import sys
import os
import time
from fastapi.testclient import TestClient

# Add the project root to sys.path
sys.path.append(os.getcwd())

def test_e2e():
    print("🚀 Starting End-to-End Test...")
    
    API_KEY = "assest_secret_key"
    HEADERS = {"X-API-Key": API_KEY}

    from backend.main import app

    with TestClient(app) as client:
        # 1. Create Workspace
        timestamp = int(time.time())
        slug = f"test-org-{timestamp}"
        print(f"⏳ Creating workspace with slug: {slug}...")
        resp = client.post("/api/workspaces", json={"name": "Test Org", "slug": slug})
        resp.raise_for_status()
        workspace = resp.json()
        workspace_id = workspace["id"]
        print(f"✅ Workspace created: {workspace_id}")
        
        # 2. Create Notion Connector
        print("⏳ Creating Notion connector...")
        resp = client.post("/api/connectors", json={
            "workspace_id": workspace_id,
            "type": "notion",
            "config": {"mock": True}
        })
        resp.raise_for_status()
        connector = resp.json()
        connector_id = connector["id"]
        print(f"✅ Connector created: {connector_id}")
        
        # 3. Trigger Ingestion
        print("⏳ Triggering ingestion...")
        resp = client.post(f"/api/connectors/{connector_id}/sync", json={
            "workspace_id": workspace_id,
            "selected_ids": ["mock-notion-engineering-handbook"]
        })
        resp.raise_for_status()
        print(f"✅ Ingestion triggered: {resp.json()}")

        # 4. Query Knowledge Base
        print("⏳ Querying knowledge base...")
        resp = client.post("/api/query", json={
            "question": "What is the refund policy?",
            "workspace_id": workspace_id
        }, headers=HEADERS)
        resp.raise_for_status()
        
        query_result = resp.json()
        print(f"✅ Query Answer: {query_result['answer']}")
        print(f"✅ Sources: {query_result['sources']}")
        
        print("\n🏆 E2E TEST PASSED!")

if __name__ == "__main__":
    test_e2e()
