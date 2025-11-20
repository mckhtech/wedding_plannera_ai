# schemas/template.py
from pydantic import BaseModel, Field, computed_field
from typing import Optional, List
from datetime import datetime

class TemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str
    prompt: str = Field(..., min_length=10)
    is_free: bool = False
    display_order: int = 0
    price: float = 0.0           # or Decimal if you prefer
    currency: str = "INR"

class TemplateCreate(TemplateBase):
    """Schema for creating a new template"""
    pass

class TemplateUpdate(BaseModel):
    """Schema for updating a template - all fields optional"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    prompt: Optional[str] = Field(None, min_length=10)
    is_free: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None
class TemplateResponse(TemplateBase):
    """Schema for template responses"""
    id: int
    preview_image: Optional[str] = None  # File path
    is_active: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime
    
    # Store request for URL generation
    _request: Optional[object] = None
    
    # Computed field for preview URL
    @computed_field
    @property
    def preview_url(self) -> Optional[str]:
        """Convert preview image path to full URL"""
        if self.preview_image:
            from app.services.storage_service import StorageService
            return StorageService.get_file_url(self.preview_image, self._request)
        return None
    
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class TemplateListItem(TemplateResponse):
    """Template item for list view - inherits preview_url from TemplateResponse"""
    is_paid: Optional[bool] = False  # ← Changed to is_paid
    
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class TemplateListResponse(BaseModel):
    templates: List[TemplateListItem]
    total: int

    class Config:
        from_attributes = True