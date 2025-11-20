from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.template import Template
from app.models.user import User
from app.schemas.template import TemplateResponse, TemplateListResponse, TemplateListItem
from app.utils.dependencies import get_current_user


router = APIRouter(prefix="/api/templates", tags=["Templates"])


# -----------------------------------------------------
# OPTIONAL USER (Does NOT throw 403 if token missing)
# -----------------------------------------------------
async def get_optional_user(Authorization: str = Header(None)) -> Optional[User]:
    """
    Allows routes to work with OR without token.
    If token exists → returns User
    If no token → returns None (NO error)
    """
    if Authorization:
        return await get_current_user(Authorization)
    return None


# -----------------------------------------------------
# AUTHENTICATED: FULL TEMPLATE LIST
# -----------------------------------------------------
@router.get("/", response_model=TemplateListResponse)
async def get_templates(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),  # Authentication required
    db: Session = Depends(get_db)
):
    """Get all active templates (requires login)"""
    query = db.query(Template).filter(Template.is_active == True)
    
    templates = query.order_by(Template.display_order).offset(skip).limit(limit).all()
    total = query.count()
    
    template_responses = []
    for template in templates:
        response = TemplateListItem.model_validate(template)
        response._request = request
        template_responses.append(response)
    
    return {"templates": template_responses, "total": total}


# -----------------------------------------------------
# AUTHENTICATED: SINGLE TEMPLATE
# -----------------------------------------------------
@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    request: Request,
    template_id: int,
    current_user: User = Depends(get_current_user),  # Authentication required
    db: Session = Depends(get_db)
):
    """Get specific template detail (requires login)"""
    template = db.query(Template).filter(
        Template.id == template_id,
        Template.is_active == True
    ).first()
    
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    
    response = TemplateResponse.model_validate(template)
    response._request = request
    return response

# -----------------------------------------------------
# PUBLIC: ALL TEMPLATES (FREE + PAID)
# -----------------------------------------------------
@router.get("/public", response_model=TemplateListResponse)
async def get_public_templates(
    request: Request,
    db: Session = Depends(get_db)
):
    """Public endpoint - anyone can view all templates"""
    
    templates = db.query(Template).filter(
        Template.is_active == True
    ).order_by(Template.display_order).all()

    template_responses = []
    for template in templates:
        response = TemplateListItem.model_validate(template)
        response._request = request
        response.is_paid = not template.is_free  # ← Changed from requires_login
        template_responses.append(response)

    return {"templates": template_responses, "total": len(template_responses)}  

# -----------------------------------------------------
# PUBLIC: FREE TEMPLATES ONLY
# -----------------------------------------------------
@router.get("/free/list", response_model=TemplateListResponse)
async def get_free_templates(
    request: Request,
    db: Session = Depends(get_db)
):
    """Public endpoint - now returns ALL templates (free + paid)"""
    
    templates = db.query(Template).filter(
        Template.is_active == True
    ).order_by(Template.display_order).all()
    
    template_responses = []
    for template in templates:
        response = TemplateListItem.model_validate(template)
        response._request = request
        response.is_paid = not template.is_free  # ← Changed from requires_login
        template_responses.append(response)
    
    return {
        "templates": template_responses,
        "total": len(template_responses)
    }


# -----------------------------------------------------
# AUTHENTICATED: CHECK ACCESS
# -----------------------------------------------------
@router.post("/{template_id}/check-access")
async def check_template_access(
    template_id: int,
    current_user: User = Depends(get_current_user),  # Must be authenticated
    db: Session = Depends(get_db)
):
    """Check if user can access a template"""
    
    template = db.query(Template).filter(Template.id == template_id).first()
    
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    
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
