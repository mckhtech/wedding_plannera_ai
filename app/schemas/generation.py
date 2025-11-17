from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.generation import GenerationStatus

class GenerationCreate(BaseModel):
    template_id: int

class GenerationResponse(BaseModel):
    id: int
    template_id: int
    user_image_path: str
    partner_image_path: Optional[str] = None
    generated_image_path: Optional[str] = None
    status: GenerationStatus
    error_message: Optional[str] = None
    has_watermark: bool
    was_free_generation: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class GenerationListResponse(BaseModel):
    generations: list[GenerationResponse]
    total: int

class GenerationStatusUpdate(BaseModel):
    status: GenerationStatus
    generated_image_path: Optional[str] = None
    error_message: Optional[str] = None