import functools
import inspect
import logging
from typing import Callable, Any, Dict

logger = logging.getLogger(__name__)


class IdempotencyStore:
    """Very small in-memory idempotency store for example purposes."""

    def __init__(self):
        self.seen = {}

    def get(self, key: str):
        return self.seen.get(key)

    def set(self, key: str, value: Any):
        self.seen[key] = value


_IDEMPOTENCY = IdempotencyStore()


def skill_wrapper(skill_name: str, idempotent: bool = True):
    """Decorator for connector functions to enforce idempotency and audit logs.

    Wrapped function must accept `params: Dict` and optional `idempotency_key: str`.
    """

    def decorator(fn: Callable[..., Any]):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapped(*args, **kwargs):
                idempotency_key = kwargs.get("idempotency_key") or kwargs.get("params", {}).get("idempotency_key")
                logger.info("skill.call.start", extra={"skill": skill_name, "idempotency_key": idempotency_key})
                if idempotent and idempotency_key:
                    prev = _IDEMPOTENCY.get(idempotency_key)
                    if prev is not None:
                        logger.info("skill.call.idempotent_hit", extra={"skill": skill_name, "idempotency_key": idempotency_key})
                        return prev
                result = await fn(*args, **kwargs)
                if idempotent and idempotency_key:
                    _IDEMPOTENCY.set(idempotency_key, result)
                logger.info("skill.call.end", extra={"skill": skill_name, "idempotency_key": idempotency_key})
                return result

            return wrapped

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            idempotency_key = kwargs.get("idempotency_key") or kwargs.get("params", {}).get("idempotency_key")
            logger.info("skill.call.start", extra={"skill": skill_name, "idempotency_key": idempotency_key})
            if idempotent and idempotency_key:
                prev = _IDEMPOTENCY.get(idempotency_key)
                if prev is not None:
                    logger.info("skill.call.idempotent_hit", extra={"skill": skill_name, "idempotency_key": idempotency_key})
                    return prev
            result = fn(*args, **kwargs)
            if idempotent and idempotency_key:
                _IDEMPOTENCY.set(idempotency_key, result)
            logger.info("skill.call.end", extra={"skill": skill_name, "idempotency_key": idempotency_key})
            return result

        return wrapped

    return decorator
