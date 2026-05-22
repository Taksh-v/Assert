from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Text, Integer
from backend.core.database import Base
import uuid

class FailedIngestion(Base):
    """
    Blueprint Layer 13: Dead Letter Queue (DLQ).
    Stores details of failed document ingests for debugging and retries.
    """
    __tablename__ = "failed_ingestions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False)
    
    source_type = Column(String, nullable=False) # slack, notion, drive
    source_url = Column(String, nullable=False)
    
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    
    # Stores the raw data if available for replay
    raw_payload = Column(JSON, nullable=True)
    
    attempts = Column(JSON, default=list) # List of timestamps and errors
    retry_count = Column(Integer, default=0)
    
    status = Column(String, default="pending") # pending, retrying, failed, resolved
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FailedIngestion(source='{self.source_type}', url='{self.source_url}')>"
