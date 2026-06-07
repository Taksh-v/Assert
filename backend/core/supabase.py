"""
Supabase client helpers.

The backend uses Supabase in two ways:
- PostgreSQL connection via DATABASE_URL
- Storage uploads via the Supabase service role key when configured
"""

from functools import lru_cache
from typing import Any, Optional

from backend.core.config import get_settings

try:
    from supabase import Client, create_client
    _HAS_SUPABASE = True
except Exception:
    Client = Any  # type: ignore[assignment]
    create_client = None
    _HAS_SUPABASE = False

settings = get_settings()


@lru_cache()
def get_supabase_client() -> Optional["Client"]:
    """Return a cached Supabase client when credentials are configured."""
    if not _HAS_SUPABASE or not settings.supabase_url:
        return None

    key = settings.supabase_service_role_key or settings.supabase_anon_key
    if not key:
        return None

    return create_client(settings.supabase_url, key)


def get_supabase_status() -> dict[str, Any]:
    """Return a lightweight status block for health checks and debugging."""
    client = get_supabase_client()
    return {
        "configured": settings.supabase_enabled,
        "client_ready": client is not None,
        "url": settings.supabase_url,
        "storage_bucket": settings.supabase_storage_bucket,
        "storage_enabled": bool(client and settings.supabase_service_role_key and settings.supabase_storage_bucket),
    }