from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from backend.api.documents import router as documents_router
from backend.api.users import get_current_user
from backend.models.user import User


def test_document_upload_async():
    """
    Verify that POST /upload accepts the document, queues the ingestion task
    to run in the background, and returns a 202 Accepted status immediately.
    """
    app = FastAPI()
    app.include_router(documents_router)
    client = TestClient(app)

    async def mock_user_dep():
        return User(id="u123", email="user@example.com")

    app.dependency_overrides[get_current_user] = mock_user_dep

    with patch("backend.api.documents.verify_workspace_access") as mock_verify_access, \
         patch("backend.api.documents.BackgroundTasks.add_task") as mock_add_task:
        
        mock_verify_access.return_value = "ws123"

        # Create a mock file
        files = {"file": ("readme.md", b"Mock Markdown Content", "text/markdown")}
        data = {"workspace_id": "ws123"}

        response = client.post("/upload", files=files, data=data)

        # Assert status code is 202 Accepted
        assert response.status_code == 202
        response_json = response.json()
        assert response_json["status"] == "processing"
        assert response_json["document_id"] is None
        assert response_json["title"] == "readme.md"

        # Assert background task was scheduled
        mock_add_task.assert_called_once()
        called_args, _ = mock_add_task.call_args
        assert called_args[0].__name__ == "run_ingestion_background"
        
        raw_doc = called_args[1]
        assert raw_doc["title"] == "readme.md"
        assert raw_doc["raw_content"] == b"Mock Markdown Content"
        assert raw_doc["metadata"]["filename"] == "readme.md"
        assert called_args[2] == "ws123"
