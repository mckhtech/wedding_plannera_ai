from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum


class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String)
    hashed_password = Column(String, nullable=True)  # Nullable for OAuth users
    auth_provider = Column(Enum(AuthProvider), default=AuthProvider.EMAIL)
    google_id = Column(String, unique=True, nullable=True)
    profile_picture = Column(String, nullable=True)
    
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    
    # Subscription info
    is_subscribed = Column(Boolean, default=False)
    credits_remaining = Column(Integer, default=2)  # Free credits for new users
    subscription_expiry = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    generations = relationship("Generation", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
