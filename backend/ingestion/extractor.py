import logging
import json
from typing import List, Dict, Any
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class EntityExtractor:
    """
    Extracts entities and relationships from text using LLMs.
    Uses lazy initialization for the Groq client to avoid SDK compatibility issues.
    """

    def __init__(self):
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self._client = None
        self._client_init_failed = False

    @property
    def client(self):
        """Lazy-init Groq client — avoids the 'proxies' TypeError on module load."""
        if self._client is not None:
            return self._client
        if self._client_init_failed or not self.api_key:
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
            return self._client
        except TypeError as e:
            # Groq SDK versions > 0.10 removed 'proxies' param from httpx
            logger.warning(f"Groq client init failed (SDK version mismatch): {e}")
            self._client_init_failed = True
            return None
        except Exception as e:
            logger.warning(f"Groq client init failed: {e}")
            self._client_init_failed = True
            return None

    async def extract_semantic_metadata(self, text: str) -> Dict[str, Any]:
        """
        Layer 5: Semantic Metadata Enrichment.
        Extracts entities, topics, keywords, and a summary in a single pass.
        """
        if not self.client:
            logger.warning("Groq API client not available, skipping enrichment")
            return {"entities": [], "topics": [], "keywords": [], "summary": ""}

        if not text or len(text) < 50:
            return {"entities": [], "topics": [], "keywords": [], "summary": ""}

        prompt = f"""
        Analyze the following text and extract semantic metadata for an enterprise knowledge base.
        
        Focus on:
        1. Entities: People, Projects, Technologies, Departments.
        2. Topics: The main subjects (e.g., Security, Onboarding, API Design).
        3. Keywords: 3-5 essential search terms.
        4. Summary: A one-sentence summary of the content.
        
        Output ONLY valid JSON in this format:
        {{
          "entities": [{"name": "...", "type": "...", "relationship": "..."}],
          "topics": ["...", "..."],
          "keywords": ["...", "..."],
          "summary": "..."
        }}
        
        Text:
        {text[:3000]}
        
        JSON Output:
        """

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a specialized metadata enrichment agent. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            
            return {
                "entities": data.get("entities", []),
                "topics": data.get("topics", []),
                "keywords": data.get("keywords", []),
                "summary": data.get("summary", "")
            }
            
        except Exception as e:
            logger.error(f"Semantic extraction error: {e}")
            return {"entities": [], "topics": [], "keywords": [], "summary": ""}

    async def extract(self, text: str) -> List[Dict[str, Any]]:
        """Legacy support for entity extraction only."""
        res = await self.extract_semantic_metadata(text)
        return res.get("entities", [])

