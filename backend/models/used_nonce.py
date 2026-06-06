from datetime import datetime
from sqlalchemy import Column, String, DateTime
from backend.core.database import Base
import uuid


class UsedNonce(Base):
    """
    Tracks state token nonces in OAuth redirection callbacks
    to prevent replay attacks.
    """
    __tablename__ = "used_nonces"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nonce = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<UsedNonce(nonce='{self.nonce[:8]}...')>"
