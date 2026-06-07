import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

class SkillContractMixin:
    """
    Mixin to provide skill contract enforcement and audit logging for connectors.
    """

    async def execute_skill(
        self,
        skill_name: str,
        handler: Callable[..., Awaitable[Dict[str, Any]]],
        inputs: Dict[str, Any],
        execution_id: str,
        workspace_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes a skill handler with standardized audit logging and response wrapping.
        """
        started_at = datetime.now(timezone.utc)
        logger.info(f"skill.call_start: {{'skill': '{skill_name}', 'execution_id': '{execution_id}', 'inputs': {inputs}}}")
        
        try:
            data = await handler(inputs, **kwargs)
            status = "success"
            error = None
        except Exception as e:
            logger.error(f"skill.error: {{'skill': '{skill_name}', 'execution_id': '{execution_id}', 'error': '{str(e)}'}}")
            status = "error"
            data = {}
            error = {"code": type(e).__name__, "message": str(e)}

        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        
        logger.info(f"skill.call_end: {{'skill': '{skill_name}', 'execution_id': '{execution_id}', 'status': '{status}', 'duration_ms': {duration_ms}}}")

        return {
            "status": status,
            "data": data,
            "error": error,
            "audit": {
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_ms": duration_ms
            }
        }
