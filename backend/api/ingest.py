import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from backend.ingestion.pipeline import IngestionPipeline

router = APIRouter(tags=["Ingestion"])
logger = logging.getLogger(__name__)


class IngestRequest(BaseModel):
    connector_id: str
    workspace_id: str


@router.post("/ingest")
async def trigger_ingestion(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger a manual ingestion for a connector.
    """
    logger.info(f"Triggering ingestion for connector: {request.connector_id}")
    
    pipeline = IngestionPipeline()
    background_tasks.add_task(pipeline.run, request.connector_id)
    
    return {"message": "Ingestion started in background", "connector_id": request.connector_id}
