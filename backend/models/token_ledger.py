from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float
from sqlalchemy.orm import relationship
from backend.core.database import Base
import uuid


class TokenLedger(Base):
    """
    Usage ledger tracking input, output, and cached token consumption
    along with estimated USD costs.
    """
    __tablename__ = "token_ledgers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_id = Column(String, ForeignKey("audit_ledgers.id"), nullable=True)
    
    model_name = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    cached_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Float, default=0.0, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    audit = relationship("AuditLedger", back_populates="tokens")

    def __repr__(self):
        return f"<TokenLedger(id='{self.id}', model_name='{self.model_name}', cost_usd='{self.cost_usd}')>"
