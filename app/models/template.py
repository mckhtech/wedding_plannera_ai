from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
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
    
    is_free = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Archive fields - NEW
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