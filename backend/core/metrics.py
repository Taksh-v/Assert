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
