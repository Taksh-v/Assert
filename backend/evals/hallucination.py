"""
Hallucination Scorer — Detects fabricated claims not supported by context.
"""
import json
import logging
from backend.evals.base_scorer import BaseScorer, ScorerResult
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class HallucinationScorer(BaseScorer):
    """
    Evaluates how much of the answer contains claims NOT supported by the context.
    
    NOTE: This scorer returns an INVERTED score:
    - 1.0 = No hallucination (all claims are grounded)
    - 0.0 = Fully hallucinated (nothing is grounded)
    """

    name = "hallucination"
    description = "Detects fabricated claims not supported by the provided context"
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

        prompt = f"""You are evaluating an AI answer for HALLUCINATION.

Hallucination means the answer contains claims, facts, numbers, names, or statements
that are NOT present in or inferable from the provided context.

Your task: Identify any hallucinated claims and score accordingly.

Score 1.0 = No hallucination detected (every claim is grounded in context)
Score 0.7 = Minor hallucination (1-2 small unsupported details)
Score 0.3 = Significant hallucination (major unsupported claims)
Score 0.0 = Fully hallucinated (most content is fabricated)

Context:
{context[:4000]}

Question: {query}

Answer: {output[:2000]}

Output ONLY valid JSON:
{{
  "score": 0.85,
  "hallucinated_claims": ["claim 1 not in context", "claim 2 not in context"],
  "reasoning": "Brief explanation"
}}"""

        try:
            model_name = settings.groq_model
            if model_name.startswith("groq/"):
                model_name = model_name.replace("groq/", "", 1)

            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a strict hallucination detector. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=model_name,
                temperature=0,
                response_format={"type": "json_object"}
            )

            data = json.loads(response.choices[0].message.content)
            claims = data.get("hallucinated_claims", [])
            reasoning = data.get("reasoning", "")
            if claims:
                reasoning += f" Hallucinated: {'; '.join(claims[:3])}"

            return ScorerResult(
                scorer_name=self.name,
                score=float(data.get("score", 0.0)),
                reasoning=reasoning,
                passed=False
            )
        except Exception as e:
            logger.warning(f"Hallucination LLM scoring failed: {e}")
            return self._fallback_evaluate(output, context)

    def _fallback_evaluate(self, output: str, context: str) -> ScorerResult:
        """Rule-based fallback: check for specific numbers/names in output but not context."""
        if not context or not output:
            return ScorerResult(self.name, 0.5, "Insufficient data for hallucination check", False)

        import re
        # Extract numbers and proper nouns from output
        output_numbers = set(re.findall(r'\b\d+\.?\d*\b', output))
        context_numbers = set(re.findall(r'\b\d+\.?\d*\b', context))

        hallucinated_numbers = output_numbers - context_numbers
        total_claims = len(output_numbers) or 1
        hallucination_rate = len(hallucinated_numbers) / total_claims

        score = max(0.0, 1.0 - hallucination_rate)
        return ScorerResult(
            scorer_name=self.name,
            score=round(score, 3),
            reasoning=f"{len(hallucinated_numbers)} numbers in answer not found in context",
            passed=False
        )
