import logging
import litellm
import os
import json
import random
import time
import asyncio
import uuid
from typing import Optional, List, Dict, Any, AsyncGenerator
from backend.core.config import get_settings
from dataclasses import dataclass
from backend.core.metrics import record_llm_call
from backend.core.langfuse_wrapper import start_run, end_run, log_event
from backend.observability.telemetry import tracer

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class LLMHealthReport:
    provider: str
    model: Optional[str]
    fallback_models: List[str]
    warnings: List[str]
    strict_validation_enabled: bool
    active_check: Optional[Dict[str, Any]] = None


class CircuitBreaker:
    """Simple circuit breaker to avoid hammering failing providers.
    
    Only trips on server-side errors (5xx) and rate limits (429).
    Client errors (400, 401, 403, 404) are the caller's fault and
    should NOT trip the breaker.
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self, exception: Exception = None):
        import time

        # Only count provider-side failures toward the circuit breaker threshold.
        if exception is not None:
            err_str = str(exception).lower()
            status_code = getattr(exception, "status_code", None)
            # Detect 4xx client errors — these should NOT trip the breaker
            if status_code and 400 <= status_code < 500 and status_code != 429:
                return
            # Heuristic: detect "400" or "bad request" in error strings from litellm
            if any(marker in err_str for marker in ["400", "bad request", "invalid", "authentication"]):
                if "429" not in err_str and "rate" not in err_str:
                    return

        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.time()

    def is_open(self) -> bool:
        import time

        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.reset_timeout:
            # reset
            self.failure_count = 0
            self.opened_at = None
            return False
        return True

# Setup safe callbacks if langfuse available
try:
    import langfuse  # type: ignore
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
except Exception:
    # Keep empty to avoid litellm internal errors
    litellm.success_callback = []
    litellm.failure_callback = []


class SharedLLMClient:
    """Shared LLM client implementation used by both core and generation modules.

    Provides an async `chat_completion` helper and a sync-compatible `chat` shim
    exposing `completions.create(...)` for backwards compatibility used in tests.
    """

    _client_init_failed = False

    def __init__(self, model_type: str = "fast"):
        # ensure callbacks are cleared to avoid litellm/langfuse oddities
        litellm.success_callback = []
        litellm.failure_callback = []
        # Reset global api_base to prevent cross-provider pollution
        litellm.api_base = None

        self.model_type = model_type
        self.provider = self._detect_provider()


        # Configure site url referer for OpenRouter
        if self.provider == "openrouter" and settings.openrouter_site_url:
            os.environ["HTTP_REFERER"] = settings.openrouter_site_url


        # choose model name
        if model_type == "smart":
            self.model = settings.company_brain_smart_model
        else:
            self.model = settings.company_brain_fast_model

        # normalize provider-specific model names
        self._normalize_model()

        # resilience primitives
        self.circuit = CircuitBreaker(failure_threshold=3, reset_timeout=60)
        # prepare fallback list from settings (string -> list)
        raw = getattr(settings, "openrouter_fallback_models", "") or ""
        self.openrouter_fallback_models = [s.strip() for s in raw.split(",") if s.strip()]
        # Build fallback policy
        self.fallback_policy = FallbackPolicy(primary=self.model, fallbacks=self.openrouter_fallback_models or [])


    def _detect_provider(self) -> str:
        return detect_llm_provider()

    async def ping(self) -> Dict[str, Any]:
        """Perform a lightweight live test against the primary model."""
        start = time.time()
        model = self._resolve_model_for_provider(self.model)
        try:
            extra_kwargs: Dict[str, Any] = {}
            if self.provider == "openrouter" and getattr(settings, "openrouter_api_key", None):
                extra_kwargs["api_key"] = settings.openrouter_api_key
            elif self.provider == "groq" and getattr(settings, "groq_api_key", None):
                extra_kwargs["api_key"] = settings.groq_api_key
            elif self.provider == "proxy":
                extra_kwargs["api_key"] = "sk-local-brain"

            api_base = settings.openrouter_api_base if self.provider == "openrouter" else getattr(settings, "litellm_proxy_url", None)

            # Very short completion for ping
            await litellm.acompletion(
                messages=[{"role": "user", "content": "ping"}],
                model=model,
                max_tokens=1,
                api_base=api_base,
                **extra_kwargs,
            )
            latency = (time.time() - start) * 1000
            return {"status": "success", "latency_ms": latency, "model": model}
        except Exception as e:
            logger.warning("LLM ping failed for model %s: %s", model, e)
            return {"status": "error", "error": str(e), "model": model}

    def _normalize_model(self) -> None:
        # simple normalization to ensure model strings match provider expectations
        if self.provider == "openrouter" and not self.model.startswith("openrouter/"):
            self.model = settings.openrouter_smart_model if self.model_type == "smart" else settings.openrouter_fast_model
        elif self.provider == "openrouter" and self.model.startswith("groq/"):
            self.model = settings.openrouter_smart_model if self.model_type == "smart" else settings.openrouter_fast_model
        elif self.provider == "groq" and not self.model.startswith("groq/"):
            self.model = settings.groq_model

    def _resolve_model_for_provider(self, model: Optional[str] = None) -> str:
        resolved_model = model or self.model

        if self.provider == "openrouter":
            if resolved_model.startswith("groq/"):
                return settings.openrouter_smart_model if "70b" in resolved_model else settings.openrouter_fast_model
            if not resolved_model.startswith("openrouter/"):
                return settings.openrouter_smart_model if self.model_type == "smart" else settings.openrouter_fast_model

        if self.provider == "groq" and not resolved_model.startswith("groq/"):
            return settings.groq_model

        return resolved_model

    def _default_max_tokens(self) -> int:
        if self.model_type == "smart":
            return int(getattr(settings, "llm_default_max_output_tokens_smart", 384))
        return int(getattr(settings, "llm_default_max_output_tokens_fast", 192))

    async def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        prompt_cache_key: Optional[str] = None,
    ) -> str:
        """Async chat completion using litellm's async API where available."""
        call_id = str(uuid.uuid4())
        logger.info("LLM call start: call_id=%s provider=%s model=%s", call_id, self.provider, self.model)
        # Check circuit breaker
        if self.circuit.is_open():
            logger.warning("Circuit open for provider %s — skipping LLM call (call_id=%s)", self.provider, call_id)
            return ""

        # Build ordered model list to try using fallback policy
        primary = self._resolve_model_for_provider(self.model)
        # regenerate fallback policy in case model resolution changed
        self.fallback_policy = FallbackPolicy(primary=primary, fallbacks=self.openrouter_fallback_models)
        models_to_try: List[str] = []
        if self.provider == "openrouter":
            # use policy ordered list then ensure fast model is last resort
            models_to_try = self.fallback_policy.ordered()
            if settings.openrouter_fast_model and settings.openrouter_fast_model not in models_to_try:
                models_to_try.append(settings.openrouter_fast_model)
        else:
            models_to_try = [primary]

        # Fallback to Groq if groq_api_key and groq_model are configured
        if getattr(settings, "groq_api_key", None) and getattr(settings, "groq_model", None):
            groq_m = settings.groq_model
            if not groq_m.startswith("groq/"):
                groq_m = f"groq/{groq_m}"
            if groq_m not in models_to_try:
                models_to_try.append(groq_m)

        attempts_per_model = max(1, getattr(settings, "openrouter_retry_attempts", 1))
        base_backoff = float(getattr(settings, "openrouter_retry_backoff_base", 0.5))
        max_tokens = max_tokens or self._default_max_tokens()

        last_exception = None

        for model in models_to_try:
            for attempt in range(attempts_per_model):
                try:
                    extra_kwargs: Dict[str, Any] = {}
                    current_api_base = None
                    if model.startswith("openrouter/"):
                        if getattr(settings, "openrouter_api_key", None):
                            extra_kwargs["api_key"] = settings.openrouter_api_key
                        current_api_base = settings.openrouter_api_base
                    elif model.startswith("groq/"):
                        if getattr(settings, "groq_api_key", None):
                            extra_kwargs["api_key"] = settings.groq_api_key
                    else:
                        if self.provider == "openrouter" and getattr(settings, "openrouter_api_key", None):
                            extra_kwargs["api_key"] = settings.openrouter_api_key
                            current_api_base = settings.openrouter_api_base
                        elif self.provider == "groq" and getattr(settings, "groq_api_key", None):
                            extra_kwargs["api_key"] = settings.groq_api_key
                        elif self.provider == "proxy":
                            extra_kwargs["api_key"] = "sk-local-brain"
                            current_api_base = getattr(settings, "litellm_proxy_url", None)

                    logger.info("Attempting LLM call provider=%s model=%s attempt=%s call_id=%s", self.provider, model, attempt, call_id)
                    # start langfuse run (best-effort)
                    lf_run = start_run(request_id=call_id, metadata={"provider": self.provider, "model": model})
                    with tracer.start_as_current_span("llm.chat_completion") as span:
                        span.set_attribute("request_id", call_id)
                        span.set_attribute("provider", self.provider)
                        span.set_attribute("model", model)
                        span.set_attribute("model_type", self.model_type)
                        span.set_attribute("attempt", attempt)
                        start = time.time()
                        response = await litellm.acompletion(
                            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            api_base=current_api_base,
                            prompt_cache_key=prompt_cache_key,
                            timeout=float(getattr(settings, "llm_request_timeout", 5.0)),
                            **extra_kwargs,
                        )
                        duration = time.time() - start
                        span.set_attribute("duration_ms", duration * 1000.0)
                    # record metrics (best-effort)
                    try:
                        record_llm_call(self.provider, model, "success", duration)
                    except Exception:
                        pass
                    try:
                        log_event(lf_run, "llm_call_success", {"duration": duration, "provider": self.provider, "model": model})
                    except Exception:
                        pass
                    try:
                        end_run(lf_run, status="ok")
                    except Exception:
                        pass
                    val = response.choices[0].message.content
                    if not val or not val.strip():
                        raise ValueError("Empty or null response content returned from LLM")
                    return val
                except Exception as e:
                    last_exception = e
                    err_str = str(e)
                    duration = time.time() - start if 'start' in locals() else 0.0
                    try:
                        record_llm_call(self.provider, model, "error", duration)
                    except Exception:
                        pass
                    try:
                        log_event(lf_run if 'lf_run' in locals() else None, "llm_call_error", {"error": err_str, "provider": self.provider, "model": model, "duration": duration})
                    except Exception:
                        pass
                    try:
                        end_run(lf_run if 'lf_run' in locals() else None, status="error")
                    except Exception:
                        pass
                    logger.warning("LLM attempt failed for model=%s attempt=%s call_id=%s: %s", model, attempt, call_id, e)
                    self.circuit.record_failure(e)
                    # if last attempt for this model, break to try next model
                    if attempt >= attempts_per_model - 1:
                        break
                    # exponential backoff with jitter
                    backoff = base_backoff * (2 ** attempt) + random.uniform(0, base_backoff)
                    await asyncio.sleep(backoff)

        # All attempts failed
        logger.error("LLM all attempts failed call_id=%s provider=%s models=%s", call_id, self.provider, models_to_try)
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("All LLM completion attempts failed.")

    async def chat_completion_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        prompt_cache_key: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Async chat completion streaming using litellm's stream=True API."""
        call_id = str(uuid.uuid4())
        logger.info("LLM stream start: call_id=%s provider=%s model=%s", call_id, self.provider, self.model)
        
        if self.circuit.is_open():
            logger.warning("Circuit open for provider %s — skipping LLM stream (call_id=%s)", self.provider, call_id)
            return

        primary = self._resolve_model_for_provider(self.model)
        self.fallback_policy = FallbackPolicy(primary=primary, fallbacks=self.openrouter_fallback_models)
        models_to_try: List[str] = []
        if self.provider == "openrouter":
            models_to_try = self.fallback_policy.ordered()
            if settings.openrouter_fast_model and settings.openrouter_fast_model not in models_to_try:
                models_to_try.append(settings.openrouter_fast_model)
        else:
            models_to_try = [primary]

        # Fallback to Groq if groq_api_key and groq_model are configured
        if getattr(settings, "groq_api_key", None) and getattr(settings, "groq_model", None):
            groq_m = settings.groq_model
            if not groq_m.startswith("groq/"):
                groq_m = f"groq/{groq_m}"
            if groq_m not in models_to_try:
                models_to_try.append(groq_m)

        attempts_per_model = max(1, getattr(settings, "openrouter_retry_attempts", 1))
        base_backoff = float(getattr(settings, "openrouter_retry_backoff_base", 0.5))
        max_tokens = max_tokens or self._default_max_tokens()

        last_exception = None

        for model in models_to_try:
            for attempt in range(attempts_per_model):
                try:
                    extra_kwargs: Dict[str, Any] = {}
                    current_api_base = None
                    if model.startswith("openrouter/"):
                        if getattr(settings, "openrouter_api_key", None):
                            extra_kwargs["api_key"] = settings.openrouter_api_key
                        current_api_base = settings.openrouter_api_base
                    elif model.startswith("groq/"):
                        if getattr(settings, "groq_api_key", None):
                            extra_kwargs["api_key"] = settings.groq_api_key
                    else:
                        if self.provider == "openrouter" and getattr(settings, "openrouter_api_key", None):
                            extra_kwargs["api_key"] = settings.openrouter_api_key
                            current_api_base = settings.openrouter_api_base
                        elif self.provider == "groq" and getattr(settings, "groq_api_key", None):
                            extra_kwargs["api_key"] = settings.groq_api_key
                        elif self.provider == "proxy":
                            extra_kwargs["api_key"] = "sk-local-brain"
                            current_api_base = getattr(settings, "litellm_proxy_url", None)

                    logger.info("Attempting LLM stream provider=%s model=%s attempt=%s call_id=%s", self.provider, model, attempt, call_id)
                    lf_run = start_run(request_id=call_id, metadata={"provider": self.provider, "model": model})
                    
                    with tracer.start_as_current_span("llm.chat_completion_stream") as span:
                        span.set_attribute("request_id", call_id)
                        span.set_attribute("provider", self.provider)
                        span.set_attribute("model", model)
                        span.set_attribute("model_type", self.model_type)
                        span.set_attribute("attempt", attempt)
                        start = time.time()
                        
                        response = await litellm.acompletion(
                            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            api_base=current_api_base,
                            stream=True,
                            prompt_cache_key=prompt_cache_key,
                            timeout=float(getattr(settings, "llm_request_timeout", 5.0)),
                            **extra_kwargs,
                        )
                        
                        yielded_any = False
                        async for chunk in response:
                            if chunk.choices and chunk.choices[0].delta.content:
                                yielded_any = True
                                yield chunk.choices[0].delta.content
                        if not yielded_any:
                            raise ValueError("Stream ended without yielding any content tokens")
                                
                        duration = time.time() - start
                        span.set_attribute("duration_ms", duration * 1000.0)
                        
                    try:
                        record_llm_call(self.provider, model, "success", duration)
                    except Exception:
                        pass
                    try:
                        log_event(lf_run, "llm_call_success", {"duration": duration, "provider": self.provider, "model": model})
                    except Exception:
                        pass
                    try:
                        end_run(lf_run, status="ok")
                    except Exception:
                        pass
                    return  # Success, exit the retry loops
                except Exception as e:
                    last_exception = e
                    err_str = str(e)
                    duration = time.time() - start if 'start' in locals() else 0.0
                    try:
                        record_llm_call(self.provider, model, "error", duration)
                    except Exception:
                        pass
                    try:
                        log_event(lf_run if 'lf_run' in locals() else None, "llm_call_error", {"error": err_str, "provider": self.provider, "model": model, "duration": duration})
                    except Exception:
                        pass
                    try:
                        end_run(lf_run if 'lf_run' in locals() else None, status="error")
                    except Exception:
                        pass
                    logger.warning("LLM stream attempt failed for model=%s attempt=%s call_id=%s: %s", model, attempt, call_id, e)
                    self.circuit.record_failure(e)
                    if attempt >= attempts_per_model - 1:
                        break
                    backoff = base_backoff * (2 ** attempt) + random.uniform(0, base_backoff)
                    await asyncio.sleep(backoff)

        logger.error("LLM all stream attempts failed call_id=%s provider=%s models=%s", call_id, self.provider, models_to_try)
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("All LLM stream attempts failed.")

    @property
    def chat(self):
        """Sync-compatible shim exposing `.completions.create(...)` used by legacy callers/tests."""
        client = self

        class Chat:
            class Completions:
                def __init__(self, outer):
                    self.outer = outer

                def create(self, *args, **kwargs):
                    # Map to litellm.completion synchronously where possible
                    model = self.outer._resolve_model_for_provider(kwargs.pop("model", self.outer.model))
                    kwargs.setdefault("max_tokens", self.outer._default_max_tokens())
                    # sync path uses explicit api_base parameter to avoid global pollution
                    pass

                    extra_kwargs = dict(kwargs)
                    if self.outer.provider == "openrouter" and getattr(settings, "openrouter_api_key", None):
                        extra_kwargs["api_key"] = settings.openrouter_api_key
                    elif self.outer.provider == "groq" and getattr(settings, "groq_api_key", None):
                        extra_kwargs["api_key"] = settings.groq_api_key
                    elif self.outer.provider == "proxy":
                        extra_kwargs["api_key"] = "sk-local-brain"

                    # Sync path: attempt primary + fallbacks with basic backoff
                    models_to_try = [model]
                    if self.outer.provider == "openrouter":
                        models_to_try.extend(self.outer.openrouter_fallback_models)
                        if settings.openrouter_fast_model not in models_to_try:
                            models_to_try.append(settings.openrouter_fast_model)

                    # Add groq model as fallback if groq key is configured
                    if getattr(settings, "groq_api_key", None) and getattr(settings, "groq_model", None):
                        groq_m = settings.groq_model
                        if not groq_m.startswith("groq/"):
                            groq_m = f"groq/{groq_m}"
                        if groq_m not in models_to_try:
                            models_to_try.append(groq_m)

                    attempts_per_model = max(1, getattr(settings, "openrouter_retry_attempts", 1))
                    base_backoff = float(getattr(settings, "openrouter_retry_backoff_base", 0.5))

                    last_exception = None
                    for m in models_to_try:
                        for attempt in range(attempts_per_model):
                            try:
                                extra_kwargs = dict(kwargs)
                                current_api_base = None
                                if m.startswith("openrouter/"):
                                    extra_kwargs["api_key"] = settings.openrouter_api_key if getattr(settings, "openrouter_api_key", None) else None
                                    current_api_base = settings.openrouter_api_base
                                elif m.startswith("groq/"):
                                    extra_kwargs["api_key"] = settings.groq_api_key if getattr(settings, "groq_api_key", None) else None
                                else:
                                    if self.outer.provider == "openrouter":
                                        extra_kwargs["api_key"] = settings.openrouter_api_key if getattr(settings, "openrouter_api_key", None) else None
                                        current_api_base = settings.openrouter_api_base
                                    elif self.outer.provider == "groq":
                                        extra_kwargs["api_key"] = settings.groq_api_key if getattr(settings, "groq_api_key", None) else None
                                    elif self.outer.provider == "proxy" and settings.litellm_proxy_url:
                                        extra_kwargs["api_key"] = "sk-local-brain"
                                        current_api_base = settings.litellm_proxy_url

                                logger.info("Sync LLM attempt provider=%s model=%s attempt=%s", self.outer.provider, m, attempt)
                                res = litellm.completion(
                                    model=m, 
                                    api_base=current_api_base, 
                                    timeout=float(getattr(settings, "llm_request_timeout", 5.0)),
                                    *args, 
                                    **extra_kwargs
                                )
                                val = res.choices[0].message.content
                                if not val or not val.strip():
                                    raise ValueError("Empty or null response content returned from LLM")
                                return res
                            except Exception as e:
                                logger.warning("Sync LLM attempt failed for model=%s attempt=%s: %s", m, attempt, e)
                                last_exception = e
                                if attempt >= attempts_per_model - 1:
                                    break
                                backoff = base_backoff * (2 ** attempt) + random.uniform(0, base_backoff)
                                time.sleep(backoff)

                    if last_exception is not None:
                        raise last_exception
                    raise RuntimeError("All LLM completion attempts failed.")

            def __init__(self):
                self.completions = self.Completions(client)

        return Chat()


@dataclass
class FallbackPolicy:
    """Simple policy describing primary + ordered fallbacks."""
    primary: str
    fallbacks: List[str]

    def ordered(self) -> List[str]:
        out = [self.primary] + [f for f in self.fallbacks if f != self.primary]
        return out


def detect_llm_provider() -> str:
    if getattr(settings, "openrouter_api_key", None):
        return "openrouter"
    if getattr(settings, "groq_api_key", None):
        return "groq"
    if getattr(settings, "litellm_proxy_url", None):
        return "proxy"
    return "local"


def build_config_hygiene_warnings() -> list[str]:
    """Warn on clearly unsafe or placeholder config values.

    This is intentionally shallow: it does not inspect `.env` contents on disk,
    only the active runtime settings object.
    """
    warnings: list[str] = []

    if getattr(settings, "app_secret_key", "") in {
        "change-me-to-a-random-64-char-string",
        "change-me",
        "",
    }:
        warnings.append("app_secret_key is using a placeholder value; set a strong random secret before production")

    if getattr(settings, "langfuse_public_key", None) == "pk-lf-public":
        warnings.append("langfuse_public_key is using the sample placeholder value")

    if getattr(settings, "langfuse_secret_key", None) == "sk-lf-secret":
        warnings.append("langfuse_secret_key is using the sample placeholder value")

    if getattr(settings, "slack_signing_secret", None) == "assest_slack_secret":
        warnings.append("slack_signing_secret is using a sample placeholder value")

    return warnings


async def validate_models_on_startup() -> list[str]:
    """Validate configured LLM providers and models at startup.

    This does lightweight checks and returns warnings — it does not fail startup.
    """
    report = await build_llm_health_report(perform_ping=settings.active_ping_on_startup)

    for warning in report.warnings:
        logger.warning("Startup model validation: %s", warning)

    if report.active_check and report.active_check.get("status") == "error":
        logger.error("LLM startup active check failed: %s", report.active_check.get("error"))
        # We add active check errors to the warnings list so they are visible to main.py
        report.warnings.append(f"Active connectivity check failed: {report.active_check.get('error')}")

    return report.warnings


async def build_llm_health_report(perform_ping: bool = False) -> LLMHealthReport:
    """Build a structured health report for the current LLM configuration.

    The report is shared by startup validation and the `/api/llm/health` endpoint.
    It intentionally performs only configuration-level checks unless perform_ping is True.
    """
    warnings: list[str] = []

    try:
        provider = detect_llm_provider()
    except Exception:
        provider = "unknown"

    model: Optional[str] = None
    fallback_models: list[str] = []

    try:
        if getattr(settings, "openrouter_api_key", None):
            model = settings.openrouter_smart_model
            fallback_models = [s.strip() for s in (settings.openrouter_fallback_models or "").split(",") if s.strip()]
            if not getattr(settings, "openrouter_fast_model", None):
                warnings.append("openrouter_fast_model is not configured")
            if "meta-llama" in (settings.openrouter_smart_model or ""):
                warnings.append("openrouter_smart_model references meta-llama — verify account access to this model")
        elif getattr(settings, "groq_api_key", None):
            model = settings.groq_model
            if not getattr(settings, "groq_model", None):
                warnings.append("groq_api_key present but groq_model not set")
        elif getattr(settings, "litellm_proxy_url", None):
            model = settings.company_brain_fast_model
        else:
            warnings.append("No LLM provider configured; using local fallback behavior")
    except Exception as e:
        logger.warning("Model validation check failed: %s", e)
        warnings.append(f"Model validation check failed: {e}")

    warnings.extend(build_config_hygiene_warnings())

    # Cross-check settings mismatches that often lead to 404/permission failures
    if getattr(settings, "openrouter_api_key", None) is None and getattr(settings, "openrouter_smart_model", None):
        warnings.append("openrouter_smart_model configured but openrouter_api_key missing")

    active_check = None
    if perform_ping:
        client = SharedLLMClient()
        active_check = await client.ping()

    return LLMHealthReport(
        provider=provider,
        model=model,
        fallback_models=fallback_models,
        warnings=warnings,
        strict_validation_enabled=bool(getattr(settings, "strict_model_validation", False)),
        active_check=active_check,
    )
