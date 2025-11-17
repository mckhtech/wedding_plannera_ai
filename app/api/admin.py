from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path
from app.database import get_db
from app.models.template import Template
from app.models.user import User, AuthProvider
from app.schemas.template import TemplateCreate, TemplateUpdate, TemplateResponse
from app.schemas.auth import LoginRequest, TokenResponse
from app.utils.dependencies import get_current_admin
from app.services.storage_service import StorageService
from app.services.auth_service import AuthService
from app.config import settings
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# ============= ADMIN LOGIN =============
@router.post("/login", response_model=TokenResponse)
async def admin_login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Admin login endpoint - only for users with is_admin=True"""
    
    # Authenticate user
    user = AuthService.authenticate_user(db, login_data.email, login_data.password)
    
    # Check if user is admin
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin privileges required."
        )
    
    # Create access token
    access_token = AuthService.create_token(user)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin
        }
    }

# ============= TEMPLATE MANAGEMENT =============
@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    name: str = Form(...),
    description: str = Form(...),
    prompt: str = Form(...),
    is_free: bool = Form(False),
    display_order: int = Form(0),
    preview_image: Optional[UploadFile] = File(None),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new template with optional preview image (Admin only)"""
    
    print(f"Creating template: name={name}, description={description}, prompt={prompt}")
    
    # Check if template name already exists
    existing = db.query(Template).filter(Template.name == name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template with this name already exists"
        )
    
    # Handle preview image upload
    preview_image_path = None
    if preview_image and preview_image.filename:
        try:
            StorageService.validate_image_file(preview_image)
            preview_image_path = await StorageService.save_upload_file(
                preview_image, 
                settings.TEMPLATE_PREVIEW_DIR
            )
            print(f"Saved preview image: {preview_image_path}")
        except Exception as e:
            print(f"Error saving preview image: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to save preview image: {str(e)}"
            )
    
    # Create template
    try:
        template = Template(
            name=name,
            description=description,
            prompt=prompt,
            preview_image=preview_image_path,
            is_free=is_free,
            display_order=display_order
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        print(f"Template created successfully: {template.id}")
        return template
    except Exception as e:
        db.rollback()
        print(f"Error creating template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )

@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    is_free: Optional[bool] = Form(None),
    display_order: Optional[int] = Form(None),
    is_active: Optional[bool] = Form(None),
    preview_image: Optional[UploadFile] = File(None),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update a template (Admin only)"""
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Update fields
    if name is not None:
        template.name = name
    if description is not None:
        template.description = description
    if prompt is not None:
        template.prompt = prompt
    if is_free is not None:
        template.is_free = is_free
    if display_order is not None:
        template.display_order = display_order
    if is_active is not None:
        template.is_active = is_active
    
    # Handle preview image update
    if preview_image and preview_image.filename:
        # Delete old preview if exists
        if template.preview_image:
            try:
                StorageService.delete_file(template.preview_image)
            except Exception as e:
                print(f"Error deleting old preview: {e}")
        
        # Upload new preview
        try:
            StorageService.validate_image_file(preview_image)
            new_preview_path = await StorageService.save_upload_file(
                preview_image,
                settings.TEMPLATE_PREVIEW_DIR
            )
            template.preview_image = new_preview_path
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to save preview image: {str(e)}"
            )
    
    try:
        db.commit()
        db.refresh(template)
        return template
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update template: {str(e)}"
        )

@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Archive a template (Admin only) - Soft delete to archive"""
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Check if already archived
    if template.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template is already archived"
        )
    
    # Archive the template
    template.is_archived = True
    template.archived_at = datetime.utcnow()
    template.is_active = False  # Also deactivate
    
    try:
        db.commit()
        return {
            "message": "Template archived successfully",
            "template_id": template_id,
            "archived_at": template.archived_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive template: {str(e)}"
        )

@router.post("/templates/{template_id}/restore")
async def restore_template(
    template_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Restore an archived template (Admin only)"""
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    if not template.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template is not archived"
        )
    
    # Restore the template
    template.is_archived = False
    template.archived_at = None
    template.is_active = True  # Reactivate
    
    try:
        db.commit()
        db.refresh(template)
        return {
            "message": "Template restored successfully",
            "template": template
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore template: {str(e)}"
        )

@router.delete("/templates/{template_id}/permanent")
async def permanently_delete_template(
    template_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Permanently delete a template (Admin only) - Can only delete archived templates"""
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Only allow permanent deletion of archived templates
    if not template.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template must be archived before permanent deletion. Archive it first."
        )
    
    # Delete preview image if exists
    if template.preview_image:
        try:
            StorageService.delete_file(template.preview_image)
        except Exception as e:
            print(f"Error deleting preview image: {e}")
    
    # Permanently delete from database
    try:
        db.delete(template)
        db.commit()
        return {
            "message": "Template permanently deleted",
            "template_id": template_id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to permanently delete template: {str(e)}"
        )

@router.get("/templates/all")
async def get_all_templates_admin(
    include_inactive: bool = False,
    show_archived: bool = False,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get all templates (Admin only) - Excludes archived by default"""
    
    query = db.query(Template)
    
    # By default, exclude archived templates
    if not show_archived:
        query = query.filter(Template.is_archived == False)
    
    # Filter by active status
    if not include_inactive and not show_archived:
        query = query.filter(Template.is_active == True)
    
    templates = query.order_by(Template.display_order).all()
    
    # Add full URL for preview images
    templates_data = []
    for template in templates:
        template_dict = {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "prompt": template.prompt,
            "preview_image": template.preview_image,
            "preview_url": StorageService.get_file_url(template.preview_image) if template.preview_image else None,
            "is_free": template.is_free,
            "is_active": template.is_active,
            "is_archived": template.is_archived,
            "archived_at": template.archived_at,
            "display_order": template.display_order,
            "usage_count": template.usage_count,
            "created_at": template.created_at,
            "updated_at": template.updated_at
        }
        templates_data.append(template_dict)
    
    return {
        "templates": templates_data,
        "total": len(templates_data)
    }

@router.get("/templates/archived")
async def get_archived_templates(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get all archived templates (Admin only)"""
    
    templates = db.query(Template).filter(
        Template.is_archived == True
    ).order_by(Template.archived_at.desc()).all()
    
    # Add full URL for preview images
    templates_data = []
    for template in templates:
        template_dict = {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "prompt": template.prompt,
            "preview_image": template.preview_image,
            "preview_url": StorageService.get_file_url(template.preview_image) if template.preview_image else None,
            "is_free": template.is_free,
            "is_active": template.is_active,
            "is_archived": template.is_archived,
            "archived_at": template.archived_at,
            "display_order": template.display_order,
            "usage_count": template.usage_count,
            "created_at": template.created_at,
            "updated_at": template.updated_at
        }
        templates_data.append(template_dict)
    
    return {
        "templates": templates_data,
        "total": len(templates_data)
    }

# ============= STATISTICS =============
@router.get("/stats")
async def get_admin_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get admin dashboard statistics"""
    from app.models.generation import Generation
    
    total_users = db.query(User).count()
    total_generations = db.query(Generation).count()
    total_templates = db.query(Template).filter(
        Template.is_active == True,
        Template.is_archived == False
    ).count()
    subscribed_users = db.query(User).filter(User.is_subscribed == True).count()
    archived_templates = db.query(Template).filter(Template.is_archived == True).count()
    
    return {
        "total_users": total_users,
        "total_generations": total_generations,
        "total_templates": total_templates,
        "subscribed_users": subscribed_users,
        "archived_templates": archived_templates
    }

# ============= USER MANAGEMENT =============
@router.get("/users")
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get all users (Admin only)"""
    users = db.query(User).offset(skip).limit(limit).all()
    return {
        "users": users,
        "total": db.query(User).count()
    }

@router.post("/users/{user_id}/grant-credits")
async def grant_credits(
    user_id: int,
    credits: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Grant credits to a user (Admin only)"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.credits_remaining += credits
    db.commit()
    
    return {
        "message": f"Granted {credits} credits to user",
        "user_id": user.id,
        "user_email": user.email,
        "new_balance": user.credits_remaining
    }

# ============= ADMIN DASHBOARD PAGE =============
@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard():
    """Serve the admin dashboard HTML page"""
    dashboard_path = Path(__file__).parent.parent / "templates" / "admin_dashboard.html"
    
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Admin dashboard not found")
    
    return FileResponse(dashboard_path)