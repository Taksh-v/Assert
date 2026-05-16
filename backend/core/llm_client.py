import logging
import httpx
from typing import Optional, Dict, Any
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class LLMClient:
    """
    Unified client for calling LLMs (Groq, Anthropic, etc.) 
    used for internal structural repair and generation.
    """
    
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY") or settings.groq_api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.model = settings.groq_model or "llama3-70b-8192"

    async def chat_completion(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Call the LLM for a chat completion."""
        if not self.api_key:
            logger.warning("GROQ_API_KEY not found. LLM features will be disabled.")
            return ""

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": temperature
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                return ""

import os
