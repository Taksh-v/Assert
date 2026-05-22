"""
Relevancy Scorer — Checks if the answer actually addresses the user's question.
"""
import json
import logging
from backend.evals.base_scorer import BaseScorer, ScorerResult
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class RelevancyScorer(BaseScorer):
    """Evaluates how relevant the answer is to the original question."""

    name = "relevancy"
    description = "Checks if the answer directly addresses the user's question"
    min_threshold = 0.5

    def __init__(self):
        self._client = None
        self._client_init_failed = False

    @property
    def client(self):
        if self._client is not None:
            return self._client
        if self._client_init_failed or not settings.groq_api_key:
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            return self._client
        except Exception as e:
            self._client_init_failed = True
            return None

    async def _evaluate(self, query: str, output: str, context: str) -> ScorerResult:
        if not self.client:
            return self._fallback_evaluate(query, output)

        prompt = f"""You are evaluating the RELEVANCY of an AI answer.

Relevancy measures whether the answer directly addresses the user's question.
An irrelevant answer might be factually correct but about the wrong topic.

Score 1.0 = Directly and completely answers the question
Score 0.5 = Partially relevant, addresses some aspects
Score 0.0 = Completely off-topic or doesn't answer the question

Question: {query}

Answer: {output[:2000]}

Output ONLY valid JSON:
{{
  "score": 0.85,
  "reasoning": "Brief explanation of your scoring"
}}"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a strict quality evaluator. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=settings.groq_model,
                temperature=0,
                response_format={"type": "json_object"}
            )

            data = json.loads(response.choices[0].message.content)
            return ScorerResult(
                scorer_name=self.name,
                score=float(data.get("score", 0.0)),
                reasoning=data.get("reasoning", ""),
                passed=False
            )
        except Exception as e:
            logger.warning(f"Relevancy LLM scoring failed: {e}")
            return self._fallback_evaluate(query, output)

    def _fallback_evaluate(self, query: str, output: str) -> ScorerResult:
        """Rule-based fallback: check if key query terms appear in the answer."""
        if not query or not output:
            return ScorerResult(self.name, 0.0, "No query or output provided", False)

        query_keywords = set(w.lower().strip("?.,!") for w in query.split() if len(w) > 3)
        output_lower = output.lower()
        matches = sum(1 for kw in query_keywords if kw in output_lower)
        score = matches / max(len(query_keywords), 1)

        return ScorerResult(
            scorer_name=self.name,
            score=round(min(score, 1.0), 3),
            reasoning=f"{matches}/{len(query_keywords)} query keywords found in answer",
            passed=False
        )
