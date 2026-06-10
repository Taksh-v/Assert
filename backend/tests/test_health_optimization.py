from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
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

    with patch("backend.core.vector_store.get_qdrant_client_ctx") as mock_qdrant_ctx:
        # Mock context manager return values
        mock_client = MagicMock()
        mock_qdrant_ctx.return_value.__enter__.return_value = mock_client
        
        # Mock collections schema to return our cache collection
        mock_col = MagicMock()
        mock_col.name = "semantic_cache"
        mock_client.get_collections.return_value.collections = [mock_col]

        # Call the health check endpoint
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["layers"]["attention"]["status"] == "connected"
        assert data["layers"]["cache"]["status"] == "connected"

        # Verify that get_qdrant_client_ctx context manager was entered exactly once
        mock_qdrant_ctx.assert_called_once()
