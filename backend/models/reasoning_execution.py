import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Text, Integer
from backend.core.database import Base

class ReasoningExecution(Base):
    """
    SQLAlchemy model to track and persist the execution lifecycle 
    of a reasoning task, enabling durable workflows and suspend/resume actions.
    """
    __tablename__ = "reasoning_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    
    # State flags: running, suspended, completed, failed
    status = Column(String, default="running", nullable=False)
    
    current_task_index = Column(Integer, default=0, nullable=False)
    
    # JSON dump of the ReasoningState dict
    state_snapshot = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ReasoningExecution(id='{self.id}', status='{self.status}', query='{self.query[:30]}...')>"
