import os, requests, time, dotenv
dotenv.load_dotenv()
token = requests.post(f"{os.getenv('SUPABASE_URL')}/auth/v1/token?grant_type=password", json={"email": "demo_test_antigravity@assest.ai", "password": "TestPassword123!"}, headers={"apikey": os.getenv("SUPABASE_ANON_KEY"), "Content-Type": "application/json"}).json()["access_token"]
workspace_id = requests.get("https://taxyhere-assest-brain.hf.space/api/workspaces", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"]

docs = requests.get(f"https://taxyhere-assest-brain.hf.space/api/documents/workspace/{workspace_id}", headers={"Authorization": f"Bearer {token}"}).json()
print(f"Total documents: {len(docs)}")
for d in docs[:5]:
    print(f"- {d['title']} (chunks: {d['chunk_count']})")
