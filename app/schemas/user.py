from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(min_length=8)

class UserGoogleAuth(BaseModel):
    google_token: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    is_subscribed: bool
    credits_remaining: int
    profile_picture: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    
class CreditsResponse(BaseModel):
    credits_remaining: int
    is_subscribed: bool
    can_generate: bool