import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_auth_flow():
    # 1. Test signup
    signup_data = {
        "email": "test_script_user@example.com",
        "password": "securepassword123",
        "full_name": "Script Verification User"
    }
    
    print("Testing signup...")
    signup_res = requests.post(f"{BASE_URL}/api/signup", json=signup_data)
    print(f"Signup response status: {signup_res.status_code}")
    if signup_res.status_code not in [200, 400]:
        print("FAIL: Signup failed unexpectedly")
        sys.exit(1)
    
    # 2. Test login
    login_data = {
        "username": signup_data["email"],
        "password": signup_data["password"]
    }
    print("Testing login...")
    login_res = requests.post(f"{BASE_URL}/api/login", data=login_data)
    print(f"Login response status: {login_res.status_code}")
    if login_res.status_code != 200:
        print("FAIL: Login failed")
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
    print("SUCCESS: Listed workspaces successfully!")
    
    # 4. Test workspace access WITHOUT token (should be 401)
    print("Testing unauthorized access (without token)...")
    unauth_res = requests.get(f"{BASE_URL}/api/workspaces")
    print(f"Unauthorized check status: {unauth_res.status_code}")
    if unauth_res.status_code != 401:
        print(f"FAIL: Expected 401, got {unauth_res.status_code}")
        sys.exit(1)
    print("SUCCESS: Unauthorized requests are rejected correctly!")

if __name__ == "__main__":
    test_auth_flow()
