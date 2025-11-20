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
    
    # ============================================
    # UPDATED CREDIT SYSTEM
    # ============================================
    # Free credits (given on signup - used for ANY template)
    free_credits_remaining = Column(Integer, default=2)
    
    # Subscription info (for future unlimited access)
    is_subscribed = Column(Boolean, default=False)
    subscription_expiry = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    generations = relationship("Generation", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payment_tokens = relationship("PaymentToken", back_populates="user", cascade="all, delete-orphan")
    
    # ============================================
    # HELPER METHODS
    # ============================================
    
    @property
    def credits_remaining(self):
        """Backward compatibility - returns free credits"""
        return self.free_credits_remaining
    
    def can_generate_with_free_template(self) -> bool:
        """
        Check if user can generate with a FREE template
        Requires: At least 1 free credit remaining
        """
        return self.free_credits_remaining > 0
    
    def can_generate_with_paid_template(self, template_id: int) -> bool:
        """
        Check if user has an unused paid token for specific paid template
        Returns True if user has purchased and not yet used a token for this template
        """
        from app.models.payment_token import PaymentToken, TokenStatus, PaymentStatus
        
        # Check for unused token with completed payment
        unused_token = next(
            (token for token in self.payment_tokens 
             if token.template_id == template_id 
             and token.status == TokenStatus.UNUSED
             and token.payment_status == PaymentStatus.COMPLETED),
            None
        )
        return unused_token is not None
    
    def get_unused_token_for_template(self, template_id: int):
        """Get the first unused paid token for a specific template"""
        from app.models.payment_token import PaymentToken, TokenStatus, PaymentStatus
        
        return next(
            (token for token in self.payment_tokens 
             if token.template_id == template_id 
             and token.status == TokenStatus.UNUSED
             and token.payment_status == PaymentStatus.COMPLETED),
            None
        )
    
    def deduct_free_credit(self) -> bool:
        """
        Deduct 1 free credit
        Returns True if successful, False if no credits available
        """
        if self.free_credits_remaining > 0:
            self.free_credits_remaining -= 1
            return True
        return False