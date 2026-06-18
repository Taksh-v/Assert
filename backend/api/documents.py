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
    
    # Upload to Supabase Storage in the background task to prevent blocking the event loop
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    bucket_name = os.environ.get("SUPABASE_STORAGE_BUCKET", "raw-storage")
    
    file_content = raw_doc.get("raw_content")
    filename = raw_doc.get("title", "document")
    content_type = raw_doc.get("metadata", {}).get("content_type", "application/octet-stream")
    
    if supabase_url and supabase_key and file_content:
        try:
            import asyncio
            from supabase import create_client, Client
            supabase: Client = create_client(supabase_url, supabase_key)
            
            import uuid
            unique_filename = f"{workspace_id}/{uuid.uuid4()}-{filename}"
            
            # Run the synchronous upload in a thread pool
            await asyncio.to_thread(
                supabase.storage.from_(bucket_name).upload,
                path=unique_filename,
                file=file_content,
                file_options={"content-type": content_type}
            )
            storage_path = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{unique_filename}"
            raw_doc["source_url"] = storage_path
            logger.info(f"Successfully uploaded {filename} to Supabase Storage at {storage_path}")
        except Exception as e:
            logger.warning(f"Failed to upload to Supabase Storage, continuing with local processing: {e}")

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
    
    # 1. Read file content incrementally and enforce a 10MB limit
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
    content = b""
    try:
        chunk_size = 1024 * 1024  # 1MB chunks
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            content += chunk
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File size exceeds the maximum limit of {MAX_UPLOAD_SIZE // (1024 * 1024)}MB."
                )
    except HTTPException:
        raise
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
        "source_url": file.filename,  # Placeholder, will be updated by background task
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
