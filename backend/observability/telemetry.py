import logging
import os
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.resources import Resource

from backend.core.database import async_session
from backend.models.failed_ingestion import FailedIngestion
from backend.core import metrics

logger = logging.getLogger(__name__)

# ── Custom File-Based Span Exporter ──────────────────────
class FileSpanExporter(SpanExporter):
    """
    OpenTelemetry Span Exporter that writes spans to a dedicated log file.
    Ensures traces are readable and persisted without needing an external collector.
    """
    def __init__(self, file_path: str):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        self.telemetry_logger = logging.getLogger("telemetry_file")
        self.telemetry_logger.propagate = False  # Avoid duplicating in general logs
        
        # Configure file handler
        handler = logging.FileHandler(file_path, mode="a")
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        self.telemetry_logger.addHandler(handler)
        self.telemetry_logger.setLevel(logging.INFO)

    def export(self, spans):
        for span in spans:
            duration_ms = (span.end_time - span.start_time) / 1_000_000 if span.end_time else 0.0
            self.telemetry_logger.info(
                f"[SPAN] Name: {span.name} | TraceId: {span.context.trace_id:032x} | "
                f"SpanId: {span.context.span_id:016x} | Duration: {duration_ms:.2f}ms | "
                f"Attributes: {dict(span.attributes)}"
            )
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


# ── Initialize OpenTelemetry ─────────────────────────────
resource = Resource(attributes={"service.name": "assest-company-brain"})
provider = TracerProvider(resource=resource)

# Export traces to logs/telemetry.log
log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs/telemetry.log"))
exporter = FileSpanExporter(log_path)
processor = SimpleSpanProcessor(exporter)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("assest.reasoning")


# ── Trace Decorator ──────────────────────────────────────
def trace_agent_step(step_name: str):
    """
    Decorator to trace an agent step or tool execution.
    Automatically logs status, latency, errors, and custom attributes to logs/telemetry.log.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(step_name) as span:
                # Capture relevant inputs (like query or workspace)
                if len(args) > 1 and isinstance(args[1], dict):
                    # For agent.run(state)
                    state = args[1]
                    if "query" in state:
                        span.set_attribute("query", state["query"])
                    if "workspace_id" in state:
                        span.set_attribute("workspace_id", state["workspace_id"])
                    if "iterations" in state:
                        span.set_attribute("iterations", state["iterations"])
                
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("status", "success")
                    
                    # Capture metrics from outputs
                    if isinstance(result, dict):
                        if "confidence_score" in result:
                            span.set_attribute("confidence", result["confidence_score"])
                        if "errors" in result and result["errors"]:
                            span.set_attribute("errors", str(result["errors"]))
                    
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)
                    raise e
        return wrapper
    return decorator


# ── Existing Ingestion Telemetry Class ──────────────────
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
    def track_run_start(connector_type: str, run_id: str):
        """Record that a sync run has started."""
        logger.info(f"Run start: connector={connector_type} run_id={run_id}")
        try:
            metrics.RETRIEVAL_PRECISION  # ensure metrics module present
        except Exception:
            pass

    @staticmethod
    def track_run_finish(connector_type: str, run_id: str, duration_seconds: float, processed: int, failed: int):
        """Record run completion metrics and timing."""
        logger.info(f"Run finish: connector={connector_type} run_id={run_id} duration={duration_seconds}s processed={processed} failed={failed}")
        try:
            # Add a simple histogram-like observation using INGESTION_LATENCY
            metrics.INGESTION_LATENCY.labels(connector_type=connector_type).observe(duration_seconds)
        except Exception:
            pass

    @staticmethod
    def track_latency(connector_type: str, duration: float):
        """Track ingestion latency in Prometheus."""
        metrics.INGESTION_LATENCY.labels(connector_type=connector_type).observe(duration)

    @staticmethod
    def track_chunking(doc_type: str, count: int):
        """Track chunking volume."""
        metrics.CHUNK_COUNT.labels(doc_type=doc_type).inc(count)
