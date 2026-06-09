import logging
import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.api.users import get_current_user
from backend.models.user import User
from backend.api.connectors import verify_workspace_access
from backend.ingestion.pipeline import IngestionPipeline
from pydantic import BaseModel

router = APIRouter(tags=["Documents"])
logger = logging.getLogger(__name__)


class DocumentUploadResponse(BaseModel):
    status: str
    document_id: Optional[str] = None
    title: str
    metadata: Dict[str, Any] = {}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    workspace_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a document directly to a workspace.
    Bypasses connector logic and goes straight to the ingestion pipeline.
    """
    # 0. Verify workspace access
    resolved_workspace_id = await verify_workspace_access(workspace_id, db, current_user)
    # 1. Read file content
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read file: {str(e)}"
        )

    # 3. Prepare raw document for ingestion pipeline
    # IngestionPipeline expects a raw_doc (dict or object)
    raw_doc = {
        "title": file.filename,
        "source_url": file.filename,  # Using filename as a placeholder source_url
        "source_type": "upload",
        "raw_content": content,
        "content_format": "auto",
        "metadata": {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content)
        }
    }

    # 4. Use IngestionPipeline to parse, embed and upsert chunks
    try:
        # IngestionPipeline uses HybridParser and VectorStore internally
        pipeline = IngestionPipeline()
        package = await pipeline.runner.process(raw_doc, resolved_workspace_id)
        
        if package.state.name == "FAILED":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER__ERROR,
                detail="Document ingestion failed during processing."
            )

        return DocumentUploadResponse(
            status="success",
            document_id=package.doc_record.id if package.doc_record else None,
            title=package.title or file.filename,
            metadata=package.metadata
        )

    except Exception as e:
        logger.exception(f"Error during document upload/ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion error: {str(e)}"
        )
    finally:
        pipeline.close()
