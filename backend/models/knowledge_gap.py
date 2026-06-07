from datetime import datetime
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Integer
from backend.core.database import Base
import uuid


class KnowledgeGap(Base):
    """
    Assest Architecture: Implicit Knowledge Tracker.
    Logs questions that the system couldn't answer well, 
    representing gaps in the organizational brain.
    """
    __tablename__ = "knowledge_gaps"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    
    query = Column(Text, nullable=False)
    max_retrieval_score = Column(Float, default=0.0)
    
    # How many times this specific gap was encountered
    frequency = Column(Integer, default=1)
    
    status = Column(String, default="open") # open, investigating, resolved
    assigned_to = Column(String, nullable=True) # Expert to fill the gap
    
    last_encountered_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<KnowledgeGap(query='{self.query[:30]}...', score={self.max_retrieval_score})>"
