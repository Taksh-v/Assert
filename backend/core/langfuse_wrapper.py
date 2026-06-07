"""Safe wrapper around Langfuse. Provides no-op functions when Langfuse is not installed or not configured.
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    import langfuse  # type: ignore
    HAS_LANGFUSE = True
except Exception:
    HAS_LANGFUSE = False


def start_run(request_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
    if not HAS_LANGFUSE:
        return None
    try:
        # Best-effort: create a run/context if API available
        if hasattr(langfuse, "create_run"):
            return langfuse.create_run(run_name=request_id or "assest-run", metadata=metadata or {})
        if hasattr(langfuse, "start_run"):
            return langfuse.start_run(name=request_id or "assest-run", meta=metadata or {})
    except Exception as e:
        logger.warning("Langfuse start_run failed: %s", e)
    return None


def end_run(run_handle, status: str = "ok"):
    if not HAS_LANGFUSE or run_handle is None:
        return
    try:
        if hasattr(run_handle, "finish"):
            run_handle.finish(status=status)
        elif hasattr(langfuse, "end_run"):
            langfuse.end_run(run_handle, status=status)
    except Exception as e:
        logger.warning("Langfuse end_run failed: %s", e)


def log_event(run_handle, name: str, payload: Dict[str, Any]):
    if not HAS_LANGFUSE or run_handle is None:
        return
    try:
        if hasattr(run_handle, "log"):
            run_handle.log(name, payload)
        elif hasattr(langfuse, "log_event"):
            langfuse.log_event(run_handle, name, payload)
    except Exception as e:
        logger.warning("Langfuse log_event failed: %s", e)
