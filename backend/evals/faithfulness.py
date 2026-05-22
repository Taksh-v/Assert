"""
Faithfulness Scorer — Checks if the answer stays faithful to the retrieved context.

Uses LLM-as-judge to evaluate whether every claim in the answer is supported
by the provided context. High faithfulness = no made-up claims.
"""
import json
import logging
from backend.evals.base_scorer import BaseScorer, ScorerResult
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class FaithfulnessScorer(BaseScorer):
    """Evaluates how faithfully the answer reflects the retrieved context."""

    name = "faithfulness"
    description = "Checks if every claim in the answer is supported by the provided context"
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
        if not self.client or not context:
            return self._fallback_evaluate(output, context)

        prompt = f"""You are evaluating the FAITHFULNESS of an AI answer.

Faithfulness measures whether every claim in the answer is supported by the provided context.
A faithful answer ONLY contains information that can be found in or directly inferred from the context.

Score 1.0 = Every claim is supported by the context
Score 0.5 = Some claims are supported, some are not
Score 0.0 = Most claims are made up or not in the context

Context:
{context[:4000]}

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
                passed=False  # Will be set by base class
            )
        except Exception as e:
            logger.warning(f"Faithfulness LLM scoring failed: {e}")
            return self._fallback_evaluate(output, context)

    def _fallback_evaluate(self, output: str, context: str) -> ScorerResult:
        """Rule-based fallback: keyword overlap check."""
        if not context or not output:
            return ScorerResult(self.name, 0.0, "No context or output provided", False)

        context_words = set(context.lower().split())
        output_words = set(output.lower().split())
        # Remove common stop words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "but", "not", "with"}
        context_words -= stop_words
        output_words -= stop_words

        if not output_words:
            return ScorerResult(self.name, 0.0, "Empty output", False)

        overlap = len(output_words & context_words) / len(output_words)
        return ScorerResult(
            scorer_name=self.name,
            score=round(min(overlap * 1.2, 1.0), 3),  # Scale up slightly
            reasoning=f"Keyword overlap: {overlap:.1%} of output words found in context",
            passed=False
        )
