from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid

class KnowledgeEvent(Base):
    """
    Layer 13: Temporal Intelligence Layer.
    Tracks organizational events, state changes, and causality over time.
    """
    __tablename__ = "knowledge_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    
    event_type = Column(String, nullable=False) # deployment, outage, policy_change, hire, project_milestone
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    # Temporal Data
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_timestamp = Column(DateTime, nullable=True) # For span events (e.g. maintenance window)
    
    # Semantic Context
    related_entity_ids = Column(JSON, default=[]) # IDs of KnowledgeObjects
    causal_links = Column(JSON, default=[]) # IDs of other KnowledgeEvents this event caused or was caused by
    
    # Lineage
    source_document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    metadata_json = Column(JSON, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace")
    document = relationship("Document")

    def __repr__(self):
        return f"<KnowledgeEvent(title='{self.title}', type='{self.event_type}', time='{self.timestamp}')>"
