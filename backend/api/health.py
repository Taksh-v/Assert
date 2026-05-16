from fastapi import APIRouter
from backend.core.config import get_settings

router = APIRouter(tags=["System"])
settings = get_settings()


@router.get("/health")
async def health_check():
    """
    Check the health of the system.
    """
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.app_env
    }
