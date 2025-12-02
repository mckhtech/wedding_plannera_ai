from pydantic import BaseModel, computed_field, Field
from typing import Optional, Dict, List
from datetime import datetime
from app.models.generation import GenerationStatus, GenerationMode

class GenerationCreate(BaseModel):
    template_id: int
    generation_mode: GenerationMode = GenerationMode.SINGLE

class GenerationResponse(BaseModel):
    id: int
    template_id: int
    generation_mode: GenerationMode
    
    # Mode 1: SINGLE
    user_image_path: Optional[str] = None
    partner_image_path: Optional[str] = None
    
    # Mode 2: COUPLE
    couple_image_path: Optional[str] = None
    
    # Mode 3: MULTI_ANGLE
    user_images: Optional[Dict[str, str]] = None
    partner_images: Optional[Dict[str, str]] = None
    
    # Output
    generated_image_path: Optional[str] = None
    watermarked_image_path: Optional[str] = None
    
    # Status
    status: GenerationStatus
    error_message: Optional[str] = None
    has_watermark: bool
    was_free_generation: bool
    
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    # Store request for URL generation (set by endpoint)
    _request: Optional[object] = None
    
    # ============================================
    # Computed fields for URLs - Mode 1 (SINGLE)
    # ============================================
    @computed_field
    @property
    def user_image_url(self) -> Optional[str]:
        """Convert user image path to full URL"""
        if self.user_image_path:
            from app.services.storage_service import StorageService
            return StorageService.get_file_url(self.user_image_path, self._request)
        return None
    
    @computed_field
    @property
    def partner_image_url(self) -> Optional[str]:
        """Convert partner image path to full URL"""
        if self.partner_image_path:
            from app.services.storage_service import StorageService
            return StorageService.get_file_url(self.partner_image_path, self._request)
        return None
    
    # ============================================
    # Computed fields for URLs - Mode 2 (COUPLE)
    # ============================================
    @computed_field
    @property
    def couple_image_url(self) -> Optional[str]:
        """Convert couple image path to full URL"""
        if self.couple_image_path:
            from app.services.storage_service import StorageService
            return StorageService.get_file_url(self.couple_image_path, self._request)
        return None
    
    # ============================================
    # Computed fields for URLs - Mode 3 (MULTI_ANGLE)
    # ============================================
    @computed_field
    @property
    def user_images_urls(self) -> Optional[Dict[str, str]]:
        """Convert user images paths to URLs"""
        if self.user_images:
            from app.services.storage_service import StorageService
            return {
                angle: StorageService.get_file_url(path, self._request)
                for angle, path in self.user_images.items()
            }
        return None
    
    @computed_field
    @property
    def partner_images_urls(self) -> Optional[Dict[str, str]]:
        """Convert partner images paths to URLs"""
        if self.partner_images:
            from app.services.storage_service import StorageService
            return {
                angle: StorageService.get_file_url(path, self._request)
                for angle, path in self.partner_images.items()
            }
        return None
    
    # ============================================
    # Output image URLs
    # ============================================
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
    
    @computed_field
    @property
    def download_url(self) -> Optional[str]:
        """Get download URL for the final image"""
        if self._request and self.status == GenerationStatus.COMPLETED:
            base_url = str(self._request.base_url).rstrip('/')
            return f"{base_url}/api/generate/{self.id}/download"
        return None
    
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class GenerationListResponse(BaseModel):
    generations: List[GenerationResponse]
    total: int

class GenerationStatusUpdate(BaseModel):
    status: GenerationStatus
    generated_image_path: Optional[str] = None
    error_message: Optional[str] = None