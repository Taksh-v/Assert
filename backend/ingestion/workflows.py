import logging
from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from backend.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


@workflow.defn
class IngestionWorkflow:
    """
    Blueprint Layer 14: Temporal-based Ingestion Orchestration.
    Provides reliability, retries, and stateful sync workflows.
    """

    @workflow.run
    async def run_sync(self, connector_id: str) -> str:
        logger.info(f"Temporal Workflow started for connector: {connector_id}")
        
        # In a real Temporal setup, this would call 'Activities'
        # for each step (Fetch, Scrub, Index, Graph)
        pipeline = IngestionPipeline()
        await pipeline.run(connector_id)
        
        return f"Sync successful for {connector_id}"
