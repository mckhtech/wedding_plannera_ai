from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum

class GenerationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class GenerationMode(str, enum.Enum):
    SINGLE = "single"           # 1 user + 1 partner (current)
    COUPLE = "couple"           # 1 couple image (both in same photo)
    MULTI_ANGLE = "multi_angle" # 3 user + 3 partner (different angles)

class Generation(Base):
    __tablename__ = "generations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    
    # Payment token (for paid templates)
    payment_token_id = Column(Integer, ForeignKey("payment_tokens.id"), nullable=True)
    
    # Generation Mode
    generation_mode = Column(Enum(GenerationMode), default=GenerationMode.SINGLE, nullable=False)
    
    # ============================================
    # Input images - Mode 1 (SINGLE) - Legacy fields
    # ============================================
    user_image_path = Column(String, nullable=True)  # Now optional for backward compatibility
    partner_image_path = Column(String, nullable=True)
    
    # ============================================
    # Input images - Mode 2 (COUPLE)
    # ============================================
    couple_image_path = Column(String, nullable=True)  # Single couple photo
    
    # ============================================
    # Input images - Mode 3 (MULTI_ANGLE)
    # ============================================
    # Stored as JSON: {"front": "path1.jpg", "left_side": "path2.jpg", "right_side": "path3.jpg"}
    user_images = Column(JSON, nullable=True)
    partner_images = Column(JSON, nullable=True)
    
    # ============================================
    # Output
    # ============================================
    generated_image_path = Column(String, nullable=True)
    watermarked_image_path = Column(String, nullable=True)
    was_free_generation = Column(Boolean, default=False)

    # Status
    status = Column(Enum(GenerationStatus), default=GenerationStatus.PENDING)
    error_message = Column(Text, nullable=True)
    
    # Metadata
    has_watermark = Column(Boolean, default=False)
    used_free_credit = Column(Boolean, default=False)  # TRUE if used free credit
    used_paid_token = Column(Boolean, default=False)   # TRUE if used paid token
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="generations")
    template = relationship("Template", back_populates="generations")
    payment_token = relationship("PaymentToken", back_populates="generation")
    
    def get_all_input_image_paths(self) -> list[str]:
        """Get all input image paths for cleanup"""
        paths = []
        
        if self.generation_mode == GenerationMode.SINGLE:
            if self.user_image_path:
                paths.append(self.user_image_path)
            if self.partner_image_path:
                paths.append(self.partner_image_path)
                
        elif self.generation_mode == GenerationMode.COUPLE:
            if self.couple_image_path:
                paths.append(self.couple_image_path)
                
        elif self.generation_mode == GenerationMode.MULTI_ANGLE:
            if self.user_images:
                paths.extend(self.user_images.values())
            if self.partner_images:
                paths.extend(self.partner_images.values())
        
        return paths