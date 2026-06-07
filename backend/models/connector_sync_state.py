from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Boolean, Text
from backend.core.database import Base

class ConnectorSyncState(Base):
    """
    Blueprint Layer 14: Incremental Sync State.
    Tracks the last successful sync point for each connector instance.
    """
    __tablename__ = "connector_sync_states"

    connector_id = Column(String, primary_key=True)
    workspace_id = Column(String, primary_key=True)
    
    # Stores the high-water mark (timestamp or opaque token)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_token = Column(String, nullable=True)
    
    # Stats for the last sync
    last_stats = Column(JSON, default=dict) # {"added": 10, "updated": 5, "deleted": 2}

    # Lease-based lock for background ingestion jobs
    is_running = Column(Boolean, default=False)
    lock_owner = Column(String, nullable=True)
    lock_acquired_at = Column(DateTime, nullable=True)
    lock_expires_at = Column(DateTime, nullable=True)

    # Last error seen while syncing this connector
    last_error = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ConnectorSyncState(id='{self.connector_id}', last_sync='{self.last_sync_at}')>"
