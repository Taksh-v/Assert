#!/bin/bash

# Assest Backend Startup Script
echo "🧠 Starting Assest Brain Backend..."

# Set PYTHONPATH to include current directory
export PYTHONPATH=$PYTHONPATH:.

# Fail fast on known broken dependency combinations.
if ! python3 - <<'PY'
import sys
from importlib.metadata import PackageNotFoundError, version

errors = []

def parse_version(value):
    parts = []
    for part in value.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)

def require_package(package_name):
    try:
        version(package_name)
    except PackageNotFoundError:
        errors.append(f"{package_name} is not installed")

for package_name in [
    "fastapi",
    "uvicorn",
    "notion-client",
    "slack-sdk",
    "presidio-analyzer",
]:
    require_package(package_name)

try:
    numpy_version = version("numpy")
    if parse_version(numpy_version) >= (2, 0):
        errors.append(f"numpy {numpy_version} is installed; required numpy>=1.26.4,<2.0")
except PackageNotFoundError:
    errors.append("numpy is not installed; required numpy>=1.26.4,<2.0")

try:
    aiohttp_version = version("aiohttp")
    parsed = parse_version(aiohttp_version)
    if parsed < (3, 10) or parsed >= (4, 0):
        errors.append(f"aiohttp {aiohttp_version} is installed; required aiohttp>=3.10,<4.0")
except PackageNotFoundError:
    errors.append("aiohttp is not installed; required aiohttp>=3.10,<4.0")

if errors:
    print("❌ Backend dependency check failed:")
    for error in errors:
        print(f"   - {error}")
    print("")
    print("Run this command, then start the backend again:")
    print("   python3 -m pip install -r backend/requirements.txt")
    print("If the full resolver is slow and only numpy/aiohttp are listed above, run:")
    print("   python3 -m pip install 'numpy>=1.26.4,<2.0' 'aiohttp>=3.10,<4.0'")
    sys.exit(1)
PY
then
    exit 1
fi

# Fix SSL Certification issues (common on macOS)
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
echo "🔒 SSL Certificates configured from: $SSL_CERT_FILE"

# Check if port 8000 is taken
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  Port 8000 is already in use. Attempting to kill the process..."
    if ! lsof -ti:8000 | xargs kill -9; then
        echo "❌ Could not stop the process using port 8000."
        echo "   Stop it manually, or run: lsof -ti:8000 | xargs kill -9"
        exit 1
    fi
    sleep 1
fi

# Start Uvicorn
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
