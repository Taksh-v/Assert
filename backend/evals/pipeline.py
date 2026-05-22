"""
Scoring Pipeline — Runs all scorers in parallel and aggregates results.

Inspired by Mastra's async evaluation framework. Scorers run non-blocking
after the response is generated, so they never slow down user-facing latency.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from backend.core.database import async_session
from backend.models.eval_score import EvalScore
from backend.evals.base_scorer import BaseScorer, ScorerResult
from backend.evals.faithfulness import FaithfulnessScorer
from backend.evals.relevancy import RelevancyScorer
from backend.evals.hallucination import HallucinationScorer
from backend.evals.completeness import CompletenessScorer

logger = logging.getLogger(__name__)


class ScoringPipeline:
    """
    Runs all registered scorers in parallel and persists results.
    
    Usage:
        pipeline = ScoringPipeline()
        results = await pipeline.evaluate(
            execution_id="...",
            workspace_id="...",
            query="What is our security policy?",
            output="Our security policy states...",
            context="[Retrieved context chunks]"
        )
    """

    def __init__(self, scorers: Optional[List[BaseScorer]] = None):
        self.scorers = scorers or [
            FaithfulnessScorer(),
            RelevancyScorer(),
            HallucinationScorer(),
            CompletenessScorer(),
        ]

    async def evaluate(
        self,
        execution_id: str,
        workspace_id: str,
        query: str,
        output: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Run all scorers in parallel and persist results.

        Returns:
            {
                "aggregate_score": 0.82,
                "scores": [ScorerResult, ...],
                "all_passed": True,
                "flagged_for_review": False
            }
        """
        logger.info(f"Scoring pipeline: Evaluating execution {execution_id} with {len(self.scorers)} scorers")

        # Run all scorers concurrently
        tasks = [
            scorer.score(query=query, output=output, context=context)
            for scorer in self.scorers
        ]
        results: List[ScorerResult] = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Scorer raised exception: {r}")
            else:
                valid_results.append(r)

        # Calculate aggregate score
        if valid_results:
            aggregate = sum(r.score for r in valid_results) / len(valid_results)
        else:
            aggregate = 0.0

        all_passed = all(r.passed for r in valid_results) if valid_results else False
        flagged = aggregate < 0.4 or any(r.score < 0.2 for r in valid_results)

        # Persist scores to database
        await self._persist_scores(execution_id, workspace_id, valid_results)

        logger.info(
            f"Scoring complete: aggregate={aggregate:.3f}, "
            f"all_passed={all_passed}, flagged={flagged}"
        )

        return {
            "aggregate_score": round(aggregate, 3),
            "scores": [r.to_dict() for r in valid_results],
            "all_passed": all_passed,
            "flagged_for_review": flagged
        }

    async def _persist_scores(
        self,
        execution_id: str,
        workspace_id: str,
        results: List[ScorerResult]
    ):
        """Persist scorer results to the eval_scores table."""
        try:
            async with async_session() as session:
                for result in results:
                    score = EvalScore(
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        scorer_name=result.scorer_name,
                        score=result.score,
                        reasoning=result.reasoning,
                        passed="true" if result.passed else "false"
                    )
                    session.add(score)
                await session.commit()
                logger.info(f"Persisted {len(results)} eval scores for execution {execution_id}")
        except Exception as e:
            logger.error(f"Failed to persist eval scores: {e}")

    async def get_scores(
        self,
        execution_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieve persisted scores for an execution."""
        from sqlalchemy import select
        async with async_session() as session:
            stmt = select(EvalScore).where(
                EvalScore.execution_id == execution_id
            ).order_by(EvalScore.created_at)
            result = await session.execute(stmt)
            scores = result.scalars().all()
            return [
                {
                    "scorer_name": s.scorer_name,
                    "score": s.score,
                    "reasoning": s.reasoning,
                    "passed": s.passed,
                    "created_at": s.created_at.isoformat()
                }
                for s in scores
            ]
