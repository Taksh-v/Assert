import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional
from backend.core.database import async_session
from backend.models.failed_ingestion import FailedIngestion
from backend.core import metrics

logger = logging.getLogger(__name__)

class Telemetry:
    """
    Blueprint Layer 13: Observability & DLQ Manager.
    Centralizes metrics tracking and handles failed ingestion routing.
    """

    @staticmethod
    async def log_failure(
        workspace_id: str,
        source_type: str,
        source_url: str,
        error: Exception,
        raw_payload: Optional[Dict[str, Any]] = None
    ):
        """Log a failed ingestion to the Dead Letter Queue (DLQ)."""
        error_msg = str(error)
        stack = traceback.format_exc()
        
        logger.error(f"Ingestion Failure in {source_type} for {source_url}: {error_msg}")
        
        # Track in Prometheus
        metrics.INGESTION_ERRORS.labels(
            connector_type=source_type,
            error_type=type(error).__name__
        ).inc()
        
        async with async_session() as session:
            failure = FailedIngestion(
                workspace_id=workspace_id,
                source_type=source_type,
                source_url=source_url,
                error_message=error_msg,
                stack_trace=stack,
                raw_payload=raw_payload,
                status="pending"
            )
            session.add(failure)
            await session.commit()
            logger.info(f"Failed ingestion routed to DLQ (ID: {failure.id})")

    @staticmethod
    def track_latency(connector_type: str, duration: float):
        """Track ingestion latency in Prometheus."""
        metrics.INGESTION_LATENCY.labels(connector_type=connector_type).observe(duration)

    @staticmethod
    def track_chunking(doc_type: str, count: int):
        """Track chunking volume."""
        metrics.CHUNK_COUNT.labels(doc_type=doc_type).inc(count)
