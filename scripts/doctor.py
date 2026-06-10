import os
import sys
from pathlib import Path

def check_env():
    print("🔍 Checking environment...")
    root_env = Path(".env")
    web_env = Path("web/.env.local")
    
    if not root_env.exists():
        print("❌ Root .env file missing!")
        return False
    
    if not web_env.exists():
        print("⚠️ web/.env.local missing. Syncing from .env...")
        sync_envs()
    
    # Check for critical vars
    with open(root_env, "r") as f:
        content = f.read()
        
    critical_vars = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_JWT_SECRET",
        "DATABASE_URL",
        "OPENROUTER_API_KEY"
    ]
    
    missing = []
    for var in critical_vars:
        if var not in content:
            missing.append(var)
            
    if missing:
        print(f"❌ Missing critical variables in .env: {', '.join(missing)}")
        return False
        
    print("✅ Environment looks good.")
    return True

def sync_envs():
    print("🔄 Syncing environment variables...")
    if not os.path.exists(".env"):
        return
        
    with open(".env", "r") as f:
        lines = f.readlines()
        
    web_lines = []
    for line in lines:
        if line.strip() and not line.startswith("#"):
            key = line.split("=")[0]
            # Prefix for Next.js if not already prefixed
            if key in ["SUPABASE_URL", "SUPABASE_ANON_KEY"]:
                web_lines.append(f"NEXT_PUBLIC_{line}")
            web_lines.append(line)
            
    # Add API URL if missing
    if not any("NEXT_PUBLIC_API_URL" in l for l in web_lines):
        web_lines.append("NEXT_PUBLIC_API_URL=http://localhost:8000\n")
        
    with open("web/.env.local", "w") as f:
        f.writelines(web_lines)
    print("✅ web/.env.local updated.")

def check_deps():
    print("📦 Checking dependencies...")
    # Check python
    print(f"🐍 Python: {sys.version.split()[0]}")
    
    # Check node
    node_version = os.popen("node -v").read().strip()
    print(f"🟢 Node: {node_version}")
    
    if not os.path.exists("web/node_modules"):
        print("⚠️ web/node_modules missing. Run 'npm install' in /web")

if __name__ == "__main__":
    check_env()
    check_deps()
