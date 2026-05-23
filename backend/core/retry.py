import time
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


def retry_sync(max_attempts: int = 3, initial_delay: float = 0.1, backoff: float = 2.0, exceptions=(Exception,)):
    """Decorator for retrying synchronous functions with exponential backoff.

    Usage:
        @retry_sync(max_attempts=3)
        def call():
            ...
    """

    def decorator(func: Callable[..., Any]):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            attempt = 1
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= max_attempts:
                        logger.exception("Retry failed after %s attempts", attempt)
                        raise
                    logger.warning("Transient error on attempt %s/%s: %s — retrying in %.2fs", attempt, max_attempts, e, delay)
                    time.sleep(delay)
                    delay *= backoff
                    attempt += 1

        return wrapper

    return decorator
