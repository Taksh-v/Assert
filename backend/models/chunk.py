from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class Chunk(Base):
    """
    Represents a semantically meaningful piece of a Document.
    Stored in Postgres for metadata and Full-Text Search.
    """
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    
    # Hierarchy & Structure (Layer 4)
    parent_id = Column(String, nullable=True) # For nested chunks
    heading_path = Column(JSON, default=[]) # Breadcrumb of headings
    chunk_type = Column(String, default="text") # text, code, table, header
    structural_metadata = Column(JSON, default={}) # For tables, lists, and specialized types
    
    content = Column(Text, nullable=False)
    content_tokens = Column(Integer, default=0)
    chunk_index = Column(Integer, default=0)
    
    # For Full-Text Search
    # On Postgres, we would use TSVECTOR. On SQLite, we use this for LIKE/MATCH
    search_content = Column(Text, nullable=True)
    
    # Metadata for ranking
    tier = Column(Integer, default=2)
    source_type = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    document_title = Column(String, nullable=True)
    permissions = Column(JSON, default={}) # ACLs (Layer 11)
    
    # Quality signals
    quality_score = Column(Float, default=1.0)
    retrieval_count = Column(Integer, default=0)
    positive_feedback = Column(Integer, default=0)
    negative_feedback = Column(Integer, default=0)
    
    # Temporal & Versioning (Layer 15)
    source_modified_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<Chunk(id='{self.id}', index={self.chunk_index})>"
