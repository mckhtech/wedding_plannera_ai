from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum

class TokenStatus(str, enum.Enum):
    UNUSED = "unused"
    USED = "used"
    REFUNDED = "refunded"
    EXPIRED = "expired"

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    
class PaymentToken(Base):
    __tablename__ = "payment_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    payment_id = Column(String, unique=True, nullable=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    amount_paid = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="INR")
    status = Column(Enum(TokenStatus), default=TokenStatus.UNUSED)
    used_at = Column(DateTime, nullable=True)
    refund_id = Column(String, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    refund_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)    
    user = relationship("User", back_populates="payment_tokens")
    template = relationship("Template", back_populates="payment_tokens")
    generation = relationship("Generation", back_populates="payment_token", uselist=False)

    def mark_as_used(self, generation_id: int = None):
        self.status = TokenStatus.USED
        self.used_at = datetime.utcnow()
        if generation_id:
            self.generation_id = generation_id

    def mark_as_refunded(self, refund_id: str, reason: str):
        """Mark token as refunded."""
        self.status = TokenStatus.REFUNDED
        self.payment_status = PaymentStatus.REFUNDED
        self.refund_id = refund_id
        self.refund_reason = reason
        self.refunded_at = datetime.utcnow()
