from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Integer, Enum, Float
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid
import enum


class FeedbackType(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NULL = "null"


class QueryLog(Base):
    """
    Log of user queries and system responses.
    """
    __tablename__ = "query_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=True)
    
    question = Column(String, nullable=False)
    answer = Column(String, nullable=True)
    sources = Column(JSON, default=[])
    # Correlate query logs with streaming request IDs for observability
    request_id = Column(String, nullable=True)
    
    feedback = Column(Enum(FeedbackType), default=FeedbackType.NULL)
    response_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Synchronous evaluation metrics
    faithfulness_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    eval_reasoning = Column(String, nullable=True)

    # Relationships
    workspace = relationship("Workspace", back_populates="query_logs")
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<QueryLog(question='{self.question[:50]}...')>"

