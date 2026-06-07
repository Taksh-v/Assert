from fastapi import APIRouter
from backend.core.config import get_settings
from backend.core.llm_impl import build_llm_health_report
import logging

router = APIRouter(tags=["LLM"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/llm/health")
async def llm_health(ping: bool = False):
    """Return structured LLM provider/model configuration health info.

    This endpoint performs lightweight configuration validation by default.
    If ping=true is passed, it performs a live connectivity test.
    """
    should_ping = ping or settings.perform_llm_ping
    report = await build_llm_health_report(perform_ping=should_ping)
    result = {
        "provider": report.provider,
        "model": report.model,
        "fallbacks": report.fallback_models,
        "strict_validation_enabled": report.strict_validation_enabled,
        "warnings": report.warnings,
        "active_check": report.active_check,
    }

    return result
