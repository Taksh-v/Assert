"""
Base Scorer — Abstract class for all quality evaluation scorers.

Inspired by Mastra's Scorer framework. Each scorer evaluates a specific
quality dimension of an agent's output (faithfulness, relevancy, etc.)
and returns a score between 0.0 and 1.0 with optional reasoning.
"""
import abc
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScorerResult:
    """Result of a single scorer evaluation."""
    scorer_name: str
    score: float  # 0.0 (worst) to 1.0 (best)
    reasoning: str  # Explanation of the score
    passed: bool  # Whether the score meets the minimum threshold

    def to_dict(self):
        return {
            "scorer_name": self.scorer_name,
            "score": round(self.score, 3),
            "reasoning": self.reasoning,
            "passed": self.passed
        }


class BaseScorer(abc.ABC):
    """
    Abstract base class for quality scorers.

    Subclasses must implement `_evaluate()` which receives:
    - query: The original user question
    - output: The agent's generated answer
    - context: The retrieved context used to generate the answer

    And returns a ScorerResult.
    """

    name: str = "base"
    description: str = ""
    min_threshold: float = 0.3  # Default minimum passing score

    async def score(
        self,
        query: str,
        output: str,
        context: str = "",
        min_threshold: Optional[float] = None
    ) -> ScorerResult:
        """
        Evaluate the output quality.
        Returns a ScorerResult with score, reasoning, and pass/fail status.
        """
        threshold = min_threshold or self.min_threshold

        try:
            result = await self._evaluate(query, output, context)
            result.passed = result.score >= threshold
            return result
        except Exception as e:
            logger.error(f"Scorer '{self.name}' failed: {e}")
            return ScorerResult(
                scorer_name=self.name,
                score=0.0,
                reasoning=f"Scorer error: {str(e)}",
                passed=False
            )

    @abc.abstractmethod
    async def _evaluate(self, query: str, output: str, context: str) -> ScorerResult:
        """Core evaluation logic. Must be implemented by subclasses."""
        pass
