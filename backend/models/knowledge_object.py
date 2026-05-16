from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class KnowledgeObject(Base):
    """
    Blueprint Layer 7: Knowledge Object Builder.
    Aggregates chunks, entities, and documents into a single logical concept.
    """
    __tablename__ = "knowledge_objects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    
    type = Column(String, nullable=False) # workflow, process, policy, incident, issue
    title = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    
    # Semantic Intelligence
    entities = Column(JSON, default=[])
    topics = Column(JSON, default=[])
    
    # Relationships & Sources
    # List of document IDs that contribute to this object
    source_document_ids = Column(JSON, default=[])
    
    # Contextual Graph Links
    # Stores relationships like ["depends_on:Project X", "updated_by:Thread Y"]
    relationships = Column(JSON, default=[])
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace")

    def __repr__(self):
        return f"<KnowledgeObject(title='{self.title}', type='{self.type}')>"
