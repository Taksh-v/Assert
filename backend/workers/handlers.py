import logging
from typing import Dict, Any
from backend.workers.task_queue import register_task_handler
from backend.workers.sync_runner import ConnectorSyncRunner

logger = logging.getLogger(__name__)

@register_task_handler("connector_sync")
async def handle_connector_sync(payload: Dict[str, Any]):
    """
    Handler for connector sync tasks.
    """
    sync_run_id = payload.get("sync_run_id")
    
    if not sync_run_id:
        raise ValueError("sync_run_id is required for connector_sync task")
    
    logger.info(f"Starting connector sync run {sync_run_id}")
    await ConnectorSyncRunner().run(sync_run_id)
    logger.info(f"Finished connector sync run {sync_run_id}")

