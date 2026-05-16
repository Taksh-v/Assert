from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class Workspace(Base):
    """
    A workspace represents a single organization or team.
    """
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    connectors = relationship("Connector", back_populates="workspace", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="workspace", cascade="all, delete-orphan")
    query_logs = relationship("QueryLog", back_populates="workspace", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="workspace", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Workspace(name='{self.name}', slug='{self.slug}')>"
