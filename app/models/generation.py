from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum

class GenerationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Generation(Base):
    __tablename__ = "generations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    
    # Payment token (for paid templates)
    payment_token_id = Column(Integer, ForeignKey("payment_tokens.id"), nullable=True)
    
    # Input images
    user_image_path = Column(String, nullable=False)
    partner_image_path = Column(String, nullable=True)
    
    # Output
    generated_image_path = Column(String, nullable=True)
    watermarked_image_path = Column(String, nullable=True)
    was_free_generation = Column(Boolean, default=False)

    # Status
    status = Column(Enum(GenerationStatus), default=GenerationStatus.PENDING)
    error_message = Column(Text, nullable=True)
    
    # Metadata - UPDATED
    has_watermark = Column(Boolean, default=False)
    used_free_credit = Column(Boolean, default=False)  # TRUE if used free credit
    used_paid_token = Column(Boolean, default=False)   # TRUE if used paid token
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="generations")
    template = relationship("Template", back_populates="generations")
    payment_token = relationship("PaymentToken", back_populates="generation")