"""Generation LLM client shim delegating to shared implementation.

This preserves `backend.generation.llm_client.LLMClient` for modules that
import the generation-specific path (some reasoning agents/tests do).
"""

from backend.core.llm_impl import SharedLLMClient as LLMClient

__all__ = ["LLMClient"]
