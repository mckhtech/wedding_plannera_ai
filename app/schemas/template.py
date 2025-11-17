from pydantic import BaseModel, Field
from typing import Optional,List
from datetime import datetime

class TemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str
    prompt: str = Field(..., min_length=10)
    is_free: bool = False
    display_order: int = 0

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

class TemplateResponse(TemplateBase):
    """Schema for template responses"""
    id: int
    preview_image: Optional[str] = None  # File path
    is_active: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True  # Updated from orm_mode for Pydantic v2


class TemplateListItem(TemplateResponse):
    preview_url: Optional[str] = None  # If you want URL in list

    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    templates: List[TemplateListItem]
    total: int

    class Config:
        from_attributes = True