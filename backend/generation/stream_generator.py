"""
Streaming Response Utility.

Wraps the LLM client with streaming capability, enabling token-by-token
responses over Server-Sent Events (SSE).
"""
import logging
import json
from typing import AsyncGenerator, List, Dict, Any
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

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.3
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
        
        if settings.litellm_proxy_url:
            litellm.api_base = settings.litellm_proxy_url

        try:
            response = await litellm.acompletion(
                messages=messages,
                model=model,
                temperature=temperature,
                stream=True
            )
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"LiteLLM Streaming failed: {e}")
            
            # Mock streaming fallback on failure
            logger.info("StreamGenerator: Using Mock Streaming fallback")
            mock_text = "This is a mock streaming response from the Assest Company Brain. The LLM Gateway failed or is not configured."
            for word in mock_text.split(" "):
                yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                import asyncio
                await asyncio.sleep(0.05)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
