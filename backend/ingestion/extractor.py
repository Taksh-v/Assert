import logging
import json
from typing import List, Dict, Any
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


import logging
import json
from typing import List, Dict, Any
from backend.core.config import get_settings
from backend.core.llm_client import LLMClient

settings = get_settings()
logger = logging.getLogger(__name__)


class EntityExtractor:
    """
    Extracts entities and relationships from text using the unified LLMClient.
    Uses the 'smart' model path for high-fidelity extraction.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="smart")

    async def extract_semantic_metadata(self, text: str) -> Dict[str, Any]:
        """
        Layer 5: Semantic Metadata Enrichment.
        Extracts categorized entities, topics, keywords, and a summary.
        Categories: Organizational, Technical, Business, Operational.
        """
        if not text or len(text) < 50:
            return {"entities": [], "topics": [], "keywords": [], "summary": ""}

        # Representative sampling for large documents to preserve global meaning
        if len(text) > 8000:
            part1 = text[:3000]
            part3 = text[-2000:]
            # Sample middle parts
            mid_len = len(text) - 5000
            mid1 = text[3000 + int(mid_len * 0.25):3000 + int(mid_len * 0.25) + 1000]
            mid2 = text[3000 + int(mid_len * 0.60):3000 + int(mid_len * 0.60) + 1000]
            sampled_text = f"{part1}\n\n[... SECTION OMITTED ...]\n\n{mid1}\n\n[... SECTION OMITTED ...]\n\n{mid2}\n\n[... SECTION OMITTED ...]\n\n{part3}"
        else:
            sampled_text = text

        prompt = f"""
        Analyze the following text and extract semantic metadata for an enterprise knowledge base.
        
        ### 1. Categorized Entities
        Extract key entities and categorize them into:
        - ORGANIZATIONAL: People, Teams, Departments, Managers.
        - TECHNICAL: APIs, Repositories, Databases, Services, Tools.
        - BUSINESS: Customers, Products, Metrics, Contracts.
        - OPERATIONAL: Incidents, Workflows, SOPs, Meetings, Tasks.

        ### 2. Relationships
        For each entity, identify its primary relationship to the context (e.g., 'owns', 'depends_on', 'caused', 'part_of').

        ### 3. Confidence
        Assign a confidence score (0.0 to 1.0) for each extraction.

        Output ONLY valid JSON in this format:
        {{
          "entities": [
            {{
              "name": "Entity Name", 
              "category": "ORGANIZATIONAL|TECHNICAL|BUSINESS|OPERATIONAL",
              "type": "Specific Type (e.g. Employee, API, Incident)",
              "relationship": "relationship_type",
              "confidence": 0.95
            }}
          ],
          "events": [
            {{
              "title": "Event Title",
              "type": "deployment|incident|policy|milestone",
              "timestamp": "ISO-8601 or approximate",
              "description": "Brief context",
              "related_entities": ["names of entities involved"]
            }}
          ],
          "topics": ["main subject 1", "main subject 2"],
          "keywords": ["term1", "term2"],
          "summary": "One-sentence summary."
        }}
        
        Text:
        {sampled_text[:8000]}
        
        JSON Output:
        """

        try:
            content = await self.llm.chat_completion(
                system_prompt="You are a specialized enterprise knowledge architect. Output ONLY valid JSON.",
                user_prompt=prompt,
                temperature=0
            )
            
            if not content:
                return {"entities": [], "topics": [], "keywords": [], "summary": ""}
                
            # Clean possible markdown noise
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            data = json.loads(content)
            
            return {
                "entities": data.get("entities", []),
                "events": data.get("events", []),
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

