"""
Eval Score Model — Stores quality evaluation results for reasoning executions.

Each scorer (faithfulness, relevancy, hallucination, completeness) produces
a score and reasoning for every reasoning run. These are persisted for
historical trend analysis and CI/CD quality gating.
"""
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey
from backend.core.database import Base
import uuid


class EvalScore(Base):
    """A single evaluation score for a reasoning execution."""
    __tablename__ = "eval_scores"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id = Column(String, ForeignKey("reasoning_executions.id"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)

    # Which scorer produced this score
    scorer_name = Column(String, nullable=False)  # e.g. "faithfulness", "relevancy"

    # The score (0.0 = worst, 1.0 = best)
    score = Column(Float, nullable=False)

    # LLM or rule-based reasoning for the score
    reasoning = Column(Text, nullable=True)

    # Whether this score passed the minimum threshold
    passed = Column(String, default="true")  # "true", "false", "skipped"

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<EvalScore(scorer='{self.scorer_name}', score={self.score}, passed={self.passed})>"
