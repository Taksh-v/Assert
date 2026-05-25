import logging
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class RetrievalPlan(BaseModel):
    intent: str = Field(default="factual", description="Intent type: root_cause, procedural, temporal, factual, predictive")
    entities: List[str] = Field(default_factory=list, description="Key entities extracted from the query")
    tasks: List[str] = Field(default_factory=list, description="Sub-tasks for multi-step retrieval")
    temporal_range: Optional[str] = Field(default=None, description="Optional time range filter")
    requires_graph: bool = Field(default=True)
    requires_temporal: bool = Field(default=False)

class QueryAnalyzer:
    """
    Layer 12: Query Understanding Engine.
    Analyzes user intent and builds a structured retrieval plan.
    """

    def __init__(self, model: str = "groq/llama-3.3-70b-versatile"):
        from backend.generation.llm_client import LLMClient
        self.client = LLMClient()
        self.model = model

    async def analyze(self, query: str) -> RetrievalPlan:
        """
        Analyze query to determine intent, entities, and retrieval tasks.
        """
        prompt = f"""
        Analyze the following user query for an enterprise knowledge system.
        Determine the intent, extract key entities, and decompose into sub-tasks if needed.

        QUERY: "{query}"

        INTENT TYPES:
        - root_cause: Investigating why something happened (outages, failures).
        - procedural: How to do something (SOPs, workflows).
        - temporal: What changed over time or state at a specific time.
        - factual: Looking for a specific person, API, or project detail.
        - predictive: Asking about risks or future impact.

        OUTPUT FORMAT (JSON):
        {{
          "intent": "intent_type",
          "entities": ["entity1", "entity2"],
          "tasks": ["sub-query 1", "sub-query 2"],
          "temporal_range": "last week | 2023 | None",
          "requires_graph": true/false,
          "requires_temporal": true/false
        }}
        """

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert retrieval architect. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            
            return RetrievalPlan(**data)
            
        except Exception as e:
            logger.error(f"Failed to analyze query: {e}")
            # Fallback to a basic plan
            return RetrievalPlan(
                intent="factual",
                entities=[],
                tasks=[str(query)],
                requires_graph=True
            )
