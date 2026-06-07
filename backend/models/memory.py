from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Text, Float
from backend.core.database import Base
import uuid

class AgenticMemory(Base):
    """
    Blueprint Layer 16: Agentic Memory Layer.
    Stores persistent observations about users, workflows, and decisions.
    """
    __tablename__ = "agentic_memories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False)
    user_id = Column(String, nullable=True) # For personalized memory
    
    # Memory Type: preference, decision, workflow, observation
    memory_type = Column(String, nullable=False)
    
    # The actual insight (e.g., "User prefers dark mode" or "Project Phoenix is delayed")
    content = Column(Text, nullable=False)
    
    # Metadata for retrieval
    tags = Column(JSON, default=[])
    importance_score = Column(Float, default=0.5) # 0 to 1
    
    # For temporal decay
    last_accessed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Linking to external persistent storage (Capsule Service)
    capsule_id = Column(String, nullable=True)

    def __repr__(self):
        return f"<AgenticMemory(type='{self.memory_type}', content='{self.content[:30]}...')>"
