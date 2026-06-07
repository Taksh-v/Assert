import time
from prometheus_client import Counter, Histogram, Summary

# Layer 13: Observability Metrics

INGESTION_LATENCY = Histogram(
    "assest_ingestion_latency_seconds",
    "Time spent ingesting a document",
    ["connector_type"]
)

INGESTION_ERRORS = Counter(
    "assest_ingestion_errors_total",
    "Total failed document ingestions",
    ["connector_type", "error_type"]
)

RETRIEVAL_PRECISION = Summary(
    "assest_retrieval_precision",
    "Estimated precision of retrieval results"
)

CHUNK_COUNT = Counter(
    "assest_chunks_total",
    "Total number of chunks indexed",
    ["doc_type"]
)


# LLM call metrics
LLM_CALLS_TOTAL = Counter(
    "assest_llm_calls_total",
    "Total LLM calls",
    ["provider", "model", "status"]
)

LLM_CALL_DURATION_SECONDS = Histogram(
    "assest_llm_call_duration_seconds",
    "LLM call duration seconds",
    ["provider", "model"]
)


def record_llm_call(provider: str, model: str, status: str, duration_seconds: float):
    try:
        LLM_CALLS_TOTAL.labels(provider=provider, model=model, status=status).inc()
        LLM_CALL_DURATION_SECONDS.labels(provider=provider, model=model).observe(duration_seconds)
    except Exception:
        # best-effort metrics
        pass


# SSE / Streaming metrics
SSE_TOKENS_TOTAL = Counter(
    "assest_sse_tokens_total",
    "Total number of SSE token events emitted",
    # Avoid high-cardinality labels; only label by workspace when available
    ["workspace_id"],
)

STREAM_LATENCY_SECONDS = Histogram(
    "assest_stream_latency_seconds",
    "Latency of streaming queries from start to done",
    # bucket defaults are OK; label by workspace to correlate
    ["workspace_id"],
)


def record_stream_token(workspace_id: str = "unknown"):
    try:
        SSE_TOKENS_TOTAL.labels(workspace_id=workspace_id).inc()
    except Exception:
        pass


def record_stream_latency(seconds: float, workspace_id: str = "unknown"):
    try:
        STREAM_LATENCY_SECONDS.labels(workspace_id=workspace_id).observe(seconds)
    except Exception:
        pass
