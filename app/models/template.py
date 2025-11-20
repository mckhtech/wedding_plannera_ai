from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Template(Base):
    __tablename__ = "templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    prompt = Column(Text, nullable=False)
    preview_image = Column(String, nullable=True)
    
    # Template type - UPDATED
    is_free = Column(Boolean, default=False)  # TRUE = free template, FALSE = paid
    is_active = Column(Boolean, default=True)
    
    # Pricing for paid templates - NEW
    price = Column(Numeric(10, 2), default=0.00)  # Price per generation
    currency = Column(String, default="INR")
    
    # Archive fields
    is_archived = Column(Boolean, default=False)
    archived_at = Column(DateTime, nullable=True)
    
    # Display order
    display_order = Column(Integer, default=0)
    
    # Usage tracking
    usage_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    generations = relationship("Generation", back_populates="template")
    payment_tokens = relationship("PaymentToken", back_populates="template")