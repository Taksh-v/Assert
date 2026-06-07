"""Multi-turn working memory.

Handles incremental summarization of conversation history to maintain context
across multiple turns without excessive token usage.
"""

import logging
from typing import List, Dict, Optional, Any
from backend.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class WorkingMemory:
    """
    Manages active context for a conversation thread.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    async def summarize_history(self, history: List[Dict[str, str]], current_summary: Optional[str] = None) -> str:
        """
        Generate or update a concise summary of the conversation so far.
        """
        if not history:
            return current_summary or ""

        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history])
        
        prompt = f"""
        Summarize the key points and context of the following conversation history.
        If a previous summary exists, incorporate it. 
        Focus on facts, user preferences, and unresolved questions.

        Previous Summary: {current_summary or "None"}
        
        New Messages:
        {history_text}
        
        Concise Summary:
        """
        
        try:
            summary = await self.llm.chat_completion("You are a conversation summarizer.", prompt)
            return summary.strip()
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return current_summary or "Summary unavailable."

    async def extract_working_context(self, question: str, summary: str) -> Dict[str, Any]:
        """
        Extract key entities or intent parameters from the current question and history summary.
        """
        prompt = f"""
        Given the conversation summary and a new question, extract any key entities, 
        intent parameters, or specific requirements.

        Summary: {summary}
        Question: {question}

        Output ONLY JSON:
        {{
            "entities": ["name1", "name2"],
            "parameters": {{"key": "value"}},
            "intent_refined": "refined question or intent"
        }}
        """
        
        try:
            res = await self.llm.chat_completion("You are a context extractor.", prompt)
            import json
            if "```json" in res:
                res = res.split("```json")[1].split("```")[0].strip()
            return json.loads(res)
        except Exception:
            return {"entities": [], "parameters": {}, "intent_refined": question}
