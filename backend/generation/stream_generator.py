"""
Streaming Response Utility.

Wraps the LLM client with streaming capability, enabling token-by-token
responses over Server-Sent Events (SSE).
"""
import logging
import json
import os
from typing import AsyncGenerator, List, Dict, Any, Optional
from backend.generation.llm_client import LLMClient
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

import litellm

class StreamGenerator:
    """Utility to generate server-sent events (SSE) for LLM streaming."""

    def __init__(self, model_type: str = "fast"):
        self.llm_client = LLMClient(model_type=model_type)
        self.model = self.llm_client.model

    def _event(self, payload: Dict[str, Any]) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = None,
        prompt_cache_key: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completions using LiteLLM and SSE.
        Yields serialized JSON events suitable for FastAPI StreamingResponse.
        """
        # Prioritize passed model, then the client's routed model
        model = model or self.model

        # Ensure Langfuse env vars are set (inherited from LLMClient logic)
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key or ""
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key or ""
        os.environ["LANGFUSE_HOST"] = settings.langfuse_host

        yield self._event(
            {
                "type": "status",
                "status": "Connecting to model stream...",
                "phase": "streaming",
                **({"request_id": request_id} if request_id else {}),
            }
        )
        
        try:
            response = await litellm.acompletion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens or self.llm_client._default_max_tokens(),
                stream=True,
                prompt_cache_key=prompt_cache_key,
                api_base=settings.litellm_proxy_url or None,
            )
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield self._event({"type": "token", "token": token, **({"request_id": request_id} if request_id else {})})
            
            yield self._event({"type": "done", **({"request_id": request_id} if request_id else {})})
            
        except Exception as e:
            logger.error(f"LiteLLM Streaming failed: {e}")
            yield self._event(
                {
                    "type": "error",
                    "error": str(e),
                    "message": f"LLM streaming failed: {str(e)}",
                    **({"request_id": request_id} if request_id else {}),
                }
            )
            yield self._event({"type": "done", **({"request_id": request_id} if request_id else {})})
