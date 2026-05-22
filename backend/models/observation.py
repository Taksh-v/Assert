"""
Observational Memory Model — Mastra-inspired compressed memory entries.

Each observation is a distilled fact extracted from raw conversation history
by the Observer agent. The Reflector agent periodically merges and prunes
observations to keep the context window stable and cache-friendly.
"""
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, Boolean
from backend.core.database import Base
import uuid


class Observation(Base):
    """A single compressed observation entry in the memory log."""
    __tablename__ = "observations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)

    # The distilled observation content (dated markdown format)
    content = Column(Text, nullable=False)

    # Priority score (0.0–1.0). Higher = more important / recent.
    # The Reflector decays this over time for old, low-signal entries.
    priority = Column(Float, default=0.5)

    # Category for structured retrieval
    # e.g. "preference", "decision", "fact", "tool_usage", "error_pattern"
    category = Column(String, default="general")

    # If the Reflector merges this observation into another, store the target ID.
    # Merged observations are excluded from the active context window.
    superseded_by = Column(String, ForeignKey("observations.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    # Approximate token count of this observation (for budget tracking)
    token_count = Column(Float, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Observation(category='{self.category}', priority={self.priority}, active={self.is_active})>"
