from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Text
from backend.core.database import Base
import uuid

class Episode(Base):
    """
    Model for storing interaction episodes.
    Used by EpisodicMemoryService to provide multi-turn reasoning context.
    """
    __tablename__ = "episodes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)
    
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    interaction = Column(Text, nullable=False)
    outcome = Column(Text, nullable=False)
    
    tags = Column(JSON, default=[])
    extra_metadata = Column(JSON, default={})
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Episode(id='{self.id}', title='{self.title}')>"
