import asyncio
import logging
import sys
import os
import httpx
from jose import jwt

# Add current directory to path
sys.path.append(os.getcwd())

from backend.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnose_oauth")

async def test_backend_connectivity(url: str):
    logger.info(f"Testing connectivity to: {url}/health")
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"{url}/health", timeout=10.0)
            logger.info(f"Connectivity result: {res.status_code}")
            if res.status_code == 200:
                logger.info("Backend is REACHABLE and HEALTHY.")
            else:
                logger.error(f"Backend returned non-200 status: {res.status_code}")
        except Exception as e:
            logger.error(f"Connectivity FAILED: {e}")

def verify_jwt_secret():
    settings = get_settings()
    secret = settings.supabase_jwt_secret
    if not secret:
        logger.error("SUPABASE_JWT_SECRET is NOT set in backend configuration.")
        return False
    
    logger.info("SUPABASE_JWT_SECRET is set.")
    try:
        payload = {"sub": "test", "email": "test@example.com"}
        token = jwt.encode(payload, secret, algorithm="HS256")
        jwt.decode(token, secret, algorithms=["HS256"])
        logger.info("JWT Secret validation: SUCCESS (HS256 works)")
        return True
    except Exception as e:
        logger.error(f"JWT Secret validation: FAILED - {e}")
        return False

async def main():
    settings = get_settings()
    logger.info("--- OAUTH DIAGNOSTIC ---")
    
    # 1. Verify Secret
    verify_jwt_secret()
    
    # 2. Check current config
    logger.info(f"SUPABASE_URL: {settings.supabase_url}")
    logger.info(f"FRONTEND_URL: {settings.frontend_url}")
    
    # 3. Test Prod Backend if known
    prod_backend = "https://Taxyhere-assest-brain.hf.space"
    await test_backend_connectivity(prod_backend)

if __name__ == "__main__":
    asyncio.run(main())
