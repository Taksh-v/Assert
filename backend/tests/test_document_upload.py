from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import zipfile
import io
import sys

from backend.api.documents import router as documents_router
from backend.api.users import get_current_user
from backend.models.user import User
from backend.ingestion.document_parser import HybridParser


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
        response = client.post("/documents/upload", files=files, data=data)

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


def test_document_upload_size_limit():
    """Verify that file uploads exceeding 10MB are rejected with 413 error."""
    app = FastAPI()
    app.include_router(documents_router)
    client = TestClient(app)

    async def mock_user_dep():
        return User(id="u123", email="user@example.com")

    app.dependency_overrides[get_current_user] = mock_user_dep

    with patch("backend.api.documents.verify_workspace_access") as mock_verify_access:
        mock_verify_access.return_value = "ws123"

        # 11MB file
        large_content = b"x" * (11 * 1024 * 1024)
        files = {"file": ("large.txt", large_content, "text/plain")}
        data = {"workspace_id": "ws123"}
        response = client.post("/documents/upload", files=files, data=data)
        assert response.status_code == 413
        assert "File size exceeds the maximum limit" in response.json()["detail"]


def create_mock_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        xml_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p>
                    <w:r>
                        <w:t>{text}</w:t>
                    </w:r>
                </w:p>
            </w:body>
        </w:document>
        """
        z.writestr("word/document.xml", xml_content)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_docx_parsing():
    """Verify that zero-dependency docx parser extracts paragraph content correctly."""
    parser = HybridParser()
    
    mock_content = create_mock_docx("Hello this is a Word Document test paragraph.")
    
    # Use parse_bytes to test tempfile creation and parsing
    res = await parser.parse_bytes(mock_content, "test_doc.docx")
    
    assert len(res) == 1
    assert res[0]["type"] == "text"
    assert "Hello this is a Word Document test paragraph" in res[0]["content"]


@pytest.mark.asyncio
async def test_graceful_missing_library_handling():
    """Verify that missing optional easyocr library doesn't crash the pipeline."""
    parser = HybridParser()
    
    # Simulate easyocr missing
    sys_modules_backup = sys.modules.get("easyocr")
    sys.modules["easyocr"] = None
    try:
        parser.ocr_reader = None
        res = parser._parse_image("mock_image.png")
        assert len(res) == 1
        assert res[0]["type"] == "error"
        assert "OCR reader (easyocr) not available" in res[0]["content"]
    finally:
        if sys_modules_backup is not None:
            sys.modules["easyocr"] = sys_modules_backup
        else:
            sys.modules.pop("easyocr", None)


@pytest.mark.asyncio
async def test_pipeline_binary_validation():
    """Verify that the ingestion pipeline processes bytes content without raising a ValidationError."""
    from backend.ingestion.pipeline import IngestionPipeline
    from backend.ingestion.document_run import IngestionPackage, IngestionState
    import types
    
    pipeline = IngestionPipeline()
    raw_doc = {
        "title": "test_document.pdf",
        "source_url": "test_document.pdf",
        "source_type": "upload",
        "raw_content": b"%PDF-1.4 mock binary content",
        "content_format": "auto",
        "metadata": {
            "filename": "test_document.pdf",
            "content_type": "application/pdf",
            "size": 28
        }
    }
    
    package = IngestionPackage(raw_doc=types.SimpleNamespace(**raw_doc), workspace_id="ws123")
    
    # Run normalizer
    from backend.ingestion.pipeline_v2 import NormalizerTransformer, ParserTransformer
    normalizer_tx = NormalizerTransformer(pipeline.normalizer)
    await normalizer_tx.transform(package)
    
    assert package.state == IngestionState.NORMALIZED
    assert isinstance(package.content, bytes)
    
    # Run parser
    parser_tx = ParserTransformer(pipeline.parser)
    with patch.object(pipeline.parser, "parse_bytes", return_value=[{"type": "text", "content": "Extracted PDF content", "metadata": {}}]) as mock_parse:
        await parser_tx.transform(package)
        mock_parse.assert_called_once_with(b"%PDF-1.4 mock binary content", "test_document.pdf")
        
    assert package.state == IngestionState.PARSED
    assert len(package.elements) == 1
    assert package.elements[0]["content"] == "Extracted PDF content"
