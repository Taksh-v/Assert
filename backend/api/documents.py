import logging
import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks
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


async def run_ingestion_background(raw_doc: dict, workspace_id: str):
    logger.info(f"Starting background document ingestion for title: {raw_doc.get('title')}")
    pipeline = IngestionPipeline()
    try:
        await pipeline.runner.process(raw_doc, workspace_id)
        logger.info(f"Successfully finished background document ingestion for: {raw_doc.get('title')}")
    except Exception as e:
        logger.exception(f"Background document ingestion failed for {raw_doc.get('title')}: {e}")
    finally:
        pipeline.close()


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    workspace_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a document directly to a workspace.
    Bypasses connector logic and goes straight to the ingestion pipeline in the background.
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

    # Queue ingestion to run in background
    background_tasks.add_task(run_ingestion_background, raw_doc, resolved_workspace_id)

    return DocumentUploadResponse(
        status="processing",
        document_id=None,
        title=file.filename,
        metadata={}
    )
