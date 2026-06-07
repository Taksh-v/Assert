from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid
import enum


class ConnectorType(str, enum.Enum):
    NOTION = "notion"
    GOOGLE_DRIVE = "google_drive"
    SLACK = "slack"
    GITHUB = "github"
    JIRA = "jira"
    WHATSAPP = "whatsapp"
    FILE_UPLOAD = "file_upload"


class ConnectorStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class Connector(Base):
    """
    A connector links a workspace to an external data source.
    """
    __tablename__ = "connectors"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    type = Column(Enum(ConnectorType, name="connectortype"), nullable=False)
    config = Column(JSON, nullable=False)  # Encrypted configuration
    status = Column(Enum(ConnectorStatus, name="connectorstatus"), default=ConnectorStatus.ACTIVE)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_cursor = Column(String, nullable=True)
    error_log = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace", back_populates="connectors")
    documents = relationship("Document", back_populates="connector", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Connector(type='{self.type}', status='{self.status}')>"
