from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Payment details
    payment_id = Column(String, unique=True)  # From payment gateway
    amount = Column(Integer, nullable=False)  # In paisa
    credits_purchased = Column(Integer, nullable=False)
    
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    
    purchased_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")