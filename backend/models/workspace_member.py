from datetime import datetime
import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class WorkspaceRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class WorkspaceMember(Base):
    """
    Join table linking Users to Workspaces with specific roles.
    Enforces tenant-level access control.
    """
    __tablename__ = "workspace_members"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(Enum(WorkspaceRole), default=WorkspaceRole.MEMBER)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="workspace_memberships")

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
    )

    def __repr__(self):
        return f"<WorkspaceMember(workspace_id='{self.workspace_id}', user_id='{self.user_id}', role='{self.role}')>"
