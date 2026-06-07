import logging
from typing import Dict, Any
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


from backend.core.llm_client import LLMClient

class DocumentClassifier:
    """
    Blueprint Layer 2: Source Normalization & Classification.
    Determines the document type to apply specialized chunking and metadata.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    async def classify(self, content: str, filename: str) -> str:
        """Classify document into a specific category using the local brain proxy."""
        if not content:
            return self._classify_locally(content, filename)

        prompt = f"""
        Classify the following document content into ONE of these categories:
        - SOP: Standard Operating Procedure / How-to guide
        - Policy: Legal, compliance, or HR policy
        - Code: Programming source code
        - MeetingNotes: Transcript or notes from a meeting
        - TechnicalManual: Deep technical documentation
        - General: Anything else

        Filename: {filename}
        Content (snippet):
        {content[:2000]}
        
        Category:
        """
        
        try:
            res = await self.llm.chat_completion("You are a specialized document classifier.", prompt)
            category = res.strip().lower()
            
            # Map to standard names
            mapping = {
                "sop": "sop",
                "policy": "policy",
                "code": "code",
                "meetingnotes": "meeting_notes",
                "technicalmanual": "tech_manual"
            }
            # Simple check if any key is in the response
            for key, val in mapping.items():
                if key in category:
                    return val
            return "general"
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return self._classify_locally(content, filename)

    def _classify_locally(self, content: str, filename: str) -> str:
        """Cheap fallback so ingestion works without an LLM key."""
        text = f"{filename}\n{content[:2000]}".lower()
        if any(marker in text for marker in ["def ", "class ", "import ", "const ", "function "]):
            return "code"
        if any(marker in text for marker in ["policy", "compliance", "leave", "payroll", "legal"]):
            return "policy"
        if any(marker in text for marker in ["steps", "procedure", "how to", "runbook", "sop"]):
            return "sop"
        if any(marker in text for marker in ["meeting", "minutes", "action items", "standup"]):
            return "meeting_notes"
        if any(marker in text for marker in ["api", "architecture", "manual", "technical"]):
            return "tech_manual"
        return "general"
