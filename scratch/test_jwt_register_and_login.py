import requests
import uuid
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_full_flow():
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    signup_data = {
        "email": unique_email,
        "password": "securepassword123",
        "full_name": "Unique Test User"
    }
    
    # 1. Test signup / register alias
    print(f"Testing signup with unique email: {unique_email}...")
    signup_res = requests.post(f"{BASE_URL}/api/register", json=signup_data)
    print(f"Signup response status: {signup_res.status_code}")
    if signup_res.status_code != 200:
        print(f"FAIL: Signup failed: {signup_res.text}")
        sys.exit(1)
        
    user_info = signup_res.json()
    print(f"Registered user: {user_info}")
    if user_info.get("email") != unique_email:
        print("FAIL: Registered user email doesn't match")
        sys.exit(1)
    print("SUCCESS: Registered successfully!")
    
    # 2. Test login
    login_data = {
        "username": unique_email,
        "password": signup_data["password"]
    }
    print("Testing login...")
    login_res = requests.post(f"{BASE_URL}/api/login", data=login_data)
    print(f"Login response status: {login_res.status_code}")
    if login_res.status_code != 200:
        print(f"FAIL: Login failed: {login_res.text}")
        sys.exit(1)
        
    res_data = login_res.json()
    token = res_data.get("access_token")
    if not token:
        print("FAIL: Access token missing in login response")
        sys.exit(1)
    print("SUCCESS: Logged in and received JWT token!")
    
    # 3. Test workspace listing with authorization header
    print("Testing workspace access with token...")
    headers = {"Authorization": f"Bearer {token}"}
    workspaces_res = requests.get(f"{BASE_URL}/api/workspaces", headers=headers)
    print(f"Workspaces response status: {workspaces_res.status_code}")
    if workspaces_res.status_code != 200:
        print("FAIL: Could not list workspaces")
        sys.exit(1)
    
    workspaces = workspaces_res.json()
    print(f"Workspaces: {workspaces}")
    if not workspaces:
        print("FAIL: No workspaces returned")
        sys.exit(1)
    
    workspace = workspaces[0]
    if workspace.get("role") != "owner":
        print(f"FAIL: Expected user to be owner of their workspace, got role: {workspace.get('role')}")
        sys.exit(1)
        
    print(f"SUCCESS: Auto-created workspace details: {workspace}")
    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_full_flow()
