import time
import asyncio
from contextlib import contextmanager
from typing import Iterator

from backend.core.config import get_settings

# Prefer Prometheus if available and enabled; otherwise fall back to printing timings.
settings = get_settings()
try:
    from prometheus_client import Histogram, Counter
    _PROM_LIB_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _PROM_LIB_AVAILABLE = False

# Only enable Prometheus exposure if the library is present and settings allow it
_PROM_AVAILABLE = _PROM_LIB_AVAILABLE and getattr(settings, "enable_prometheus", False)


if _PROM_AVAILABLE:
    _INGESTION_TRANSFORM_HIST = Histogram(
        "ingestion_transform_seconds",
        "Time spent transforming documents",
        ["stage"],
    )
    _INGESTION_ERRORS = Counter(
        "ingestion_errors_total", "Total ingestion errors", ["stage"]
    )


@contextmanager
def timer(stage: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if _PROM_AVAILABLE:
            _INGESTION_TRANSFORM_HIST.labels(stage=stage).observe(elapsed)
        else:
            print(f"METRIC TIMER {stage}: {elapsed:.3f}s")


async def run_with_timeout(coro, timeout: float):
    """Await `coro` with a timeout. Raises asyncio.TimeoutError on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        if _PROM_AVAILABLE:
            _INGESTION_ERRORS.labels(stage="timeout").inc()
        raise
