from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class AuditLedger(Base):
    """
    Compliance audit trail logging all system events, reasoning executions,
    RAG retrievals, and tool calls.
    """
    __tablename__ = "audit_ledgers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    
    action_type = Column(String, nullable=False)  # 'query', 'tool_call', 'retrieval', etc.
    execution_tier = Column(String, nullable=True) # 'fast_rag', 'full_swarm', etc.
    
    payload = Column(JSON, default={}, nullable=False)
    signature = Column(String, nullable=True)      # Future-proofing for tamper verification

    # Relationships
    workspace = relationship("Workspace", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")
    tokens = relationship("TokenLedger", back_populates="audit", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AuditLedger(id='{self.id}', action_type='{self.action_type}', timestamp='{self.timestamp}')>"
