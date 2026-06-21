from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from backend.api.health import router as health_router


def test_health_check_optimized():
    """
    Verify that the /health endpoint executes successfully and consolidates
    Qdrant client connections into a single connection, avoiding lock contention.
    """
    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)

    with patch("backend.core.vector_store.get_qdrant_client_ctx") as mock_qdrant_ctx, \
         patch("backend.api.health.async_session") as mock_session_ctx, \
         patch("backend.core.redis_client.redis_health_check", new_callable=AsyncMock) as mock_redis_health:
        
        # Mock Qdrant context manager return values
        mock_client = MagicMock()
        mock_qdrant_ctx.return_value.__enter__.return_value = mock_client
        
        # Mock collections schema to return our cache collection
        mock_col = MagicMock()
        mock_col.name = "semantic_cache"
        mock_client.get_collections.return_value.collections = [mock_col]

        # Mock Redis health check to return connected
        mock_redis_health.return_value = {"status": "connected", "engine": "Redis"}

        # Mock DB session context manager and execution
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock()

        # Call the health check endpoint
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["layers"]["attention"]["status"] == "connected"
        assert data["layers"]["cache_l2"]["status"] == "connected"
        assert data["layers"]["memory"]["status"] == "connected"
        assert data["layers"]["cache_l1"]["status"] == "connected"

        # Verify that get_qdrant_client_ctx context manager was entered exactly once
        mock_qdrant_ctx.assert_called_once()
