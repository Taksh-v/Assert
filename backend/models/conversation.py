from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class Conversation(Base):
    """
    Groups a series of queries/responses into a single thread.
    Similar to a 'Chat' in ChatGPT.
    """
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace", back_populates="conversations")
    messages = relationship("QueryLog", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation(title='{self.title}', id='{self.id}')>"
