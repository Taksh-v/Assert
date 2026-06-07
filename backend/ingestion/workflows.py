import logging
from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from backend.ingestion.activities import (
        fetch_documents_activity,
        scrub_document_activity,
        index_document_activity,
        build_graph_activity,
        record_failed_ingestion_activity,
    )

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

        # 1. Fetch Documents Activity
        docs = await workflow.execute_activity(
            fetch_documents_activity,
            connector_id,
            start_to_close_timeout=timedelta(minutes=5),
        )

        if not docs:
            logger.info("No documents fetched or connector inactive")
            return f"Sync complete: 0 documents fetched for {connector_id}"

        processed_count = 0
        for doc in docs:
            workspace_id = doc["workspace_id"]
            connector_id = doc["connector_id"]
            source_type = doc["source_type"]
            source_url = doc["source_url"]

            try:
                # 2. PII Scrubbing / Parsing / Enrichment Activity
                scrubbed = await workflow.execute_activity(
                    scrub_document_activity,
                    doc,
                    start_to_close_timeout=timedelta(minutes=2),
                )

                # 3. Indexing & Persistence Activity
                index_res = await workflow.execute_activity(
                    index_document_activity,
                    scrubbed,
                    workspace_id,
                    connector_id,
                    start_to_close_timeout=timedelta(minutes=2),
                )

                # 4. Graph Construction Activity
                await workflow.execute_activity(
                    build_graph_activity,
                    index_res,
                    workspace_id,
                    start_to_close_timeout=timedelta(minutes=2),
                )

                processed_count += 1
            except Exception as e:
                # Failures route to DLQ
                error_msg = str(e)
                logger.error(f"Failed to ingest document {source_url}: {error_msg}")
                await workflow.execute_activity(
                    record_failed_ingestion_activity,
                    workspace_id,
                    source_type,
                    source_url,
                    error_msg,
                    start_to_close_timeout=timedelta(minutes=1),
                )

        return f"Sync successful for {connector_id}: processed {processed_count}/{len(docs)} documents"

