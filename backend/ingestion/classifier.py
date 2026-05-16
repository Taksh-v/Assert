import logging
from typing import Dict, Any
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DocumentClassifier:
    """
    Blueprint Layer 2: Source Normalization & Classification.
    Determines the document type to apply specialized chunking and metadata.
    """

    def __init__(self):
        self._client = None
        self._client_init_failed = False
        self.model = settings.groq_model

    @property
    def client(self):
        """Lazy-init Groq client to avoid 'proxies' TypeError."""
        if self._client is not None:
            return self._client
        if self._client_init_failed or not settings.groq_api_key:
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            return self._client
        except TypeError as e:
            logger.warning(f"Groq client init failed (SDK version mismatch): {e}")
            self._client_init_failed = True
            return None
        except Exception as e:
            logger.warning(f"Groq client init failed: {e}")
            self._client_init_failed = True
            return None

    async def classify(self, content: str, filename: str) -> str:
        """Classify document into a specific category."""
        if not content or not self.client:
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
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0,
            )
            category = response.choices[0].message.content.strip().lower()
            
            # Map to standard names
            mapping = {
                "sop": "sop",
                "policy": "policy",
                "code": "code",
                "meetingnotes": "meeting_notes",
                "technicalmanual": "tech_manual"
            }
            return mapping.get(category, "general")
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
