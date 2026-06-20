import logging
from typing import Optional
from backend.core.config import get_settings
from backend.core.llm_client import LLMClient

logger = logging.getLogger(__name__)
settings = get_settings()


class ChunkContextualizer:
    """
    SOTA Ingestion: Contextual Retrieval Layer.
    Prepends a short, LLM-generated document-level summary to each chunk.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="fast")
        self.enabled = settings.enable_contextual_retrieval

    async def contextualize(
        self, doc_title: str, doc_content: str, chunk_content: str
    ) -> str:
        """
        Generate a 1-2 sentence context summary for a chunk within a document.
        """
        if not self.enabled:
            return ""

        # Limit document content size for safety and token efficiency
        doc_summary_text = doc_content[:15000].strip() if doc_content else ""
        if not doc_summary_text:
            return ""

        prompt = f"""<document>
{doc_summary_text}
</document>

Here is the chunk we want to situate within the whole document:
<chunk>
{chunk_content}
</chunk>

Please give a short succinct context of 1 to 2 sentences to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
"""

        try:
            context = await self.llm.chat_completion(
                system_prompt="You are a precise context annotator. Output ONLY the succinct context text.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=64,
                prompt_cache_key="contextualizer:v1",
            )
            context = context.strip()
            # Clean up any potential markdown wrap if the model didn't follow instruction
            if context.startswith("Context:"):
                context = context[len("Context:"):].strip()
            return context
        except Exception as e:
            logger.warning(
                f"Contextual retrieval generation failed for chunk in '{doc_title}'. "
                f"Using title fallback: {e}"
            )
            # Fallback heuristic
            return f"This chunk is part of the document titled '{doc_title}'."
