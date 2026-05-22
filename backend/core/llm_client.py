import logging
import litellm
import os
from typing import Optional, Dict, Any
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Configure LiteLLM for Langfuse tracing with safety fallback
try:
    import langfuse
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
except (ImportError, AttributeError) as e:
    logger.warning(f"Langfuse integration in LiteLLM failed (likely version mismatch): {e}. Proceeding without tracing.")
    litellm.success_callback = []
    litellm.failure_callback = []

class LLMClient:
    """
    Unified client for calling LLMs (Groq, Anthropic, local Ollama) 
    routed via the local LiteLLM gateway for zero cost.
    """
    
    def __init__(self, model_type: str = "fast"):
        # Explicitly clear callbacks to prevent internal LiteLLM/Langfuse crashes
        litellm.success_callback = []
        litellm.failure_callback = []
        
        # Configure Langfuse for manual tracing if needed later
        
        # Point to local LiteLLM proxy if configured
        if settings.litellm_proxy_url:
            litellm.api_base = settings.litellm_proxy_url
            
        # Select the routed model name based on type
        if model_type == "smart":
            self.model = settings.company_brain_smart_model
        else:
            self.model = settings.company_brain_fast_model

    async def chat_completion(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Call the LLM for a chat completion using LiteLLM."""
        try:
            # Ensure local proxy is used for every call
            api_base = settings.litellm_proxy_url

            response = await litellm.acompletion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=self.model,
                temperature=temperature,
                api_base=api_base,
                # In dev, if proxy isn't up, LiteLLM might try to go to OpenAI.
                # Setting a dummy key prevents some provider-check failures.
                api_key="sk-local-brain" if "openai" in self.model else None
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"LiteLLM call failed: {e}")
            return ""