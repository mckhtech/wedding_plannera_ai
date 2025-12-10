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
    FLEXIBLE = "flexible"  # NEW: 1-3 images per person (auto-detect)
    COUPLE = "couple"      # UNCHANGED: 1 image with both people

class Generation(Base):
    __tablename__ = "generations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    payment_token_id = Column(Integer, ForeignKey("payment_tokens.id"), nullable=True)
    
    # Generation Mode
    generation_mode = Column(
        Enum(GenerationMode, values_callable=lambda x: [e.value for e in x]),
        default=GenerationMode.FLEXIBLE,
        nullable=False
    )

    # ============================================
    # Mode 1: FLEXIBLE (1-3 images per person)
    # ============================================
    # Stored as JSON arrays: ["path1.jpg", "path2.jpg", "path3.jpg"]
    user_images = Column(JSON, nullable=True)     # 1-3 user images
    partner_images = Column(JSON, nullable=True)  # 1-3 partner images
    
    # ============================================
    # Mode 2: COUPLE (1 image with both)
    # ============================================
    couple_image_path = Column(String, nullable=True)
    
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
    used_free_credit = Column(Boolean, default=False)
    used_paid_token = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="generations")
    template = relationship("Template", back_populates="generations")
    payment_token = relationship("PaymentToken", back_populates="generation")
    
    def get_all_input_image_paths(self) -> list[str]:
        """Get all input image paths for cleanup"""
        paths = []
        
        if self.generation_mode == GenerationMode.FLEXIBLE:
            if self.user_images:
                paths.extend(self.user_images)
            if self.partner_images:
                paths.extend(self.partner_images)
                
        elif self.generation_mode == GenerationMode.COUPLE:
            if self.couple_image_path:
                paths.append(self.couple_image_path)
        
        return paths