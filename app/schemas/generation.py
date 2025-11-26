# schemas/generation.py
from pydantic import BaseModel, computed_field
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
    watermarked_image_path: Optional[str] = None
    status: GenerationStatus
    error_message: Optional[str] = None
    has_watermark: bool
    was_free_generation: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    # Store request for URL generation (set by endpoint)
    _request: Optional[object] = None
    
    # Computed fields for URLs
    @computed_field
    @property
    def user_image_url(self) -> str:
        """Convert user image path to full URL"""
        from app.services.storage_service import StorageService
        return StorageService.get_file_url(self.user_image_path, self._request)
    
    @computed_field
    @property
    def partner_image_url(self) -> Optional[str]:
        """Convert partner image path to full URL"""
        if self.partner_image_path:
            from app.services.storage_service import StorageService
            return StorageService.get_file_url(self.partner_image_path, self._request)
        return None
    
    @computed_field
    @property
    def generated_image_url(self) -> Optional[str]:
        """Convert generated image path to full URL"""
        if self.generated_image_path:
            from app.services.storage_service import StorageService
            return StorageService.get_file_url(self.generated_image_path, self._request)
        return None
    
    @computed_field
    @property
    def watermarked_image_url(self) -> Optional[str]:
        """Convert watermarked image path to full URL"""
        if self.watermarked_image_path:
            from app.services.storage_service import StorageService
            return StorageService.get_file_url(self.watermarked_image_path, self._request)
        return None
    
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
class GenerationListResponse(BaseModel):
    generations: list[GenerationResponse]
    total: int

class GenerationStatusUpdate(BaseModel):
    status: GenerationStatus
    generated_image_path: Optional[str] = None
    error_message: Optional[str] = None

