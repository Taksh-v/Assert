from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class Document(Base):
    """
    Metadata for an ingested document.
    """
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    connector_id = Column(String, ForeignKey("connectors.id"), nullable=True, index=True)
    
    source_url = Column(String, nullable=False)
    title = Column(String, nullable=True)
    document_type = Column(String, default="general") # sop, policy, code, etc.
    mime_type = Column(String, nullable=True)
    content_hash = Column(String, nullable=False)
    chunk_count = Column(Integer, default=0)
    
    tier = Column(Integer, default=2)  # 1: Canonical, 2: Derived, 3: Conversational
    tags = Column(JSON, default=[])
    
    last_ingested_at = Column(DateTime, default=datetime.utcnow)
    is_stale = Column(Boolean, default=False)
    
    # Layer 15: Temporal Versioning
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    previous_version_id = Column(String, nullable=True) # Pointer to old version for lineage

    # Relationships
    workspace = relationship("Workspace", back_populates="documents")
    connector = relationship("Connector", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(title='{self.title}', url='{self.source_url}')>"
