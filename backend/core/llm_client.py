"""Thin wrapper re-exporting the shared LLM client implementation.

This module preserves the historical import path `backend.core.llm_client.LLMClient`
so existing callers and tests continue to work while the implementation is
centralized in `backend.core.llm_impl.SharedLLMClient`.
"""

from backend.core.llm_impl import SharedLLMClient as LLMClient

__all__ = ["LLMClient"]