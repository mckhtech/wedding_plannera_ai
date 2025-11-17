from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.template import Template
from app.models.user import User
from app.schemas.template import TemplateResponse, TemplateListResponse
from app.utils.dependencies import get_current_user
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api/templates", tags=["Templates"])

@router.get("/", response_model=TemplateListResponse)
async def get_templates(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active templates"""
    query = db.query(Template).filter(Template.is_active == True)
    
    # If user is not subscribed, show only free templates and premium templates (locked)
    templates = query.order_by(Template.display_order).offset(skip).limit(limit).all()
    total = query.count()
    
    # Add user-specific info (can access or not)
    for template in templates:
        # You can add custom fields here based on user subscription
        pass
    
    return {
        "templates": templates,
        "total": total
    }

@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific template"""
    template = db.query(Template).filter(
        Template.id == template_id,
        Template.is_active == True
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    return template

@router.get("/free/list", response_model=TemplateListResponse)
async def get_free_templates(db: Session = Depends(get_db)):
    """Get all free templates (no authentication required for preview)"""
    templates = db.query(Template).filter(
        Template.is_free == True,
        Template.is_active == True
    ).order_by(Template.display_order).all()
    
    return {
        "templates": templates,
        "total": len(templates)
    }

@router.post("/{template_id}/check-access")
async def check_template_access(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if user can access this template"""
    template = db.query(Template).filter(Template.id == template_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Check if user can access
    can_access = (
        template.is_free or 
        current_user.is_subscribed or 
        current_user.credits_remaining > 0
    )
    
    return {
        "can_access": can_access,
        "is_free": template.is_free,
        "requires_subscription": not template.is_free,
        "user_credits": current_user.credits_remaining,
        "user_subscribed": current_user.is_subscribed
    }