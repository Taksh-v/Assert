import logging
import litellm
import os
import json
from typing import Optional, List, Dict, Any
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

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

        self.model_type = model_type
        self.provider = self._detect_provider()

        # Configure api base based on provider/config
        if self.provider == "openrouter":
            litellm.api_base = settings.openrouter_api_base
            if settings.openrouter_site_url:
                os.environ["HTTP_REFERER"] = settings.openrouter_site_url
        elif settings.litellm_proxy_url:
            litellm.api_base = settings.litellm_proxy_url

        # choose model name
        if model_type == "smart":
            self.model = settings.company_brain_smart_model
        else:
            self.model = settings.company_brain_fast_model

        # normalize provider-specific model names
        self._normalize_model()

    def _detect_provider(self) -> str:
        if getattr(settings, "openrouter_api_key", None):
            return "openrouter"
        if getattr(settings, "groq_api_key", None):
            return "groq"
        if getattr(settings, "litellm_proxy_url", None):
            return "proxy"
        return "local"

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

    async def chat_completion(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Async chat completion using litellm's async API where available."""
        try:
            model = self._resolve_model_for_provider(self.model)
            api_base = settings.openrouter_api_base if self.provider == "openrouter" else getattr(settings, "litellm_proxy_url", None)
            extra_kwargs: Dict[str, Any] = {}
            if self.provider == "openrouter" and getattr(settings, "openrouter_api_key", None):
                extra_kwargs["api_key"] = settings.openrouter_api_key
            elif self.provider == "groq" and getattr(settings, "groq_api_key", None):
                extra_kwargs["api_key"] = settings.groq_api_key
            elif self.provider == "proxy":
                extra_kwargs["api_key"] = "sk-local-brain"

            response = await litellm.acompletion(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                model=model,
                temperature=temperature,
                api_base=api_base,
                **extra_kwargs,
            )
            return response.choices[0].message.content
        except Exception as e:
            err_str = str(e)
            logger.warning(f"Async LLM completion failed: {e}")
            # Retry with a cheaper/default OpenRouter model if endpoint not found
            if self.provider == "openrouter" and ("No endpoints found" in err_str or "NotFoundError" in err_str):
                try:
                    fallback_model = settings.openrouter_fast_model
                    logger.info(f"Retrying async completion with fallback model: {fallback_model}")
                    response = await litellm.acompletion(
                        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                        model=fallback_model,
                        temperature=temperature,
                        api_base=settings.openrouter_api_base,
                        api_key=(settings.openrouter_api_key if getattr(settings, "openrouter_api_key", None) else None),
                    )
                    return response.choices[0].message.content
                except Exception as e2:
                    logger.warning(f"Fallback async completion also failed: {e2}")
            return ""

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
                    # ensure api_base set for sync path
                    if self.outer.provider == "openrouter":
                        litellm.api_base = settings.openrouter_api_base
                    elif self.outer.provider == "proxy" and settings.litellm_proxy_url:
                        litellm.api_base = settings.litellm_proxy_url

                    extra_kwargs = dict(kwargs)
                    if self.outer.provider == "openrouter" and getattr(settings, "openrouter_api_key", None):
                        extra_kwargs["api_key"] = settings.openrouter_api_key
                    elif self.outer.provider == "groq" and getattr(settings, "groq_api_key", None):
                        extra_kwargs["api_key"] = settings.groq_api_key
                    elif self.outer.provider == "proxy":
                        extra_kwargs["api_key"] = "sk-local-brain"

                    try:
                        return litellm.completion(model=model, *args, **extra_kwargs)
                    except Exception as e:
                        err = str(e)
                        logger.warning(f"Sync LLM completion failed: {e}")
                        # Retry with fallback OpenRouter model when available
                        if self.outer.provider == "openrouter" and ("No endpoints found" in err or "NotFoundError" in err):
                            try:
                                fb_model = settings.openrouter_fast_model
                                logger.info(f"Retrying sync completion with fallback model: {fb_model}")
                                if getattr(settings, "openrouter_api_key", None):
                                    extra_kwargs["api_key"] = settings.openrouter_api_key
                                litellm.api_base = settings.openrouter_api_base
                                return litellm.completion(model=fb_model, *args, **extra_kwargs)
                            except Exception as e3:
                                logger.warning(f"Fallback sync completion also failed: {e3}")
                        # Provide a minimal mock-like response to keep callers robust in tests/dev
                        class MockResp:
                            def __init__(self, content):
                                self.choices = [type('Choice', (), {'message': type('Message', (), {'content': content})()})]

                        return MockResp("")

            def __init__(self):
                self.completions = self.Completions(client)

        return Chat()
