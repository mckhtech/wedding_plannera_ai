from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models.generation import Generation, GenerationStatus
from app.models.template import Template
from app.models.user import User
from app.schemas.generation import GenerationResponse, GenerationListResponse
from app.utils.dependencies import get_current_user, check_user_credits
from app.services.storage_service import StorageService
from app.services.image_generation_service import ImageGenerationService
from pathlib import Path

router = APIRouter(prefix="/api/generate", tags=["Image Generation"])

async def process_generation(
    generation_id: int,
    user_image_path: str,
    partner_image_path: Optional[str],
    prompt: str,
    add_watermark: bool,
    db_session
):
    """Background task to process image generation"""
    try:
        # Update status to processing
        generation = db_session.query(Generation).filter(Generation.id == generation_id).first()
        generation.status = GenerationStatus.PROCESSING
        db_session.commit()
        
        # Generate image
        image_service = ImageGenerationService()
        generated_path, watermarked_path = await image_service.generate_image(
            user_image_path,
            partner_image_path,
            prompt,
            add_watermark
        )
        
        # Update generation record
        generation.generated_image_path = generated_path
        generation.watermarked_image_path = watermarked_path
        generation.status = GenerationStatus.COMPLETED
        generation.completed_at = datetime.utcnow()
        generation.has_watermark = add_watermark
        
        db_session.commit()
        
    except Exception as e:
        # Update with error
        generation = db_session.query(Generation).filter(Generation.id == generation_id).first()
        generation.status = GenerationStatus.FAILED
        generation.error_message = str(e)
        db_session.commit()

@router.post("/", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
async def create_generation(
    template_id: int,
    user_image: UploadFile = File(...),
    partner_image: Optional[UploadFile] = File(None),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new image generation request"""
    
    # Get template
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Check if user can access this template
    if not template.is_free:
        if current_user.credits_remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient credits. Please purchase more credits."
            )
    
    # Validate images
    StorageService.validate_image_file(user_image)
    if partner_image:
        StorageService.validate_image_file(partner_image)
    
    # Save uploaded images
    user_image_path = await StorageService.save_upload_file(user_image, "uploads")
    partner_image_path = None
    if partner_image:
        partner_image_path = await StorageService.save_upload_file(partner_image, "uploads")
    
    # Determine if watermark should be added
    add_watermark = not current_user.is_subscribed and not template.is_free
    
    # Create generation record
    generation = Generation(
        user_id=current_user.id,
        template_id=template_id,
        user_image_path=user_image_path,
        partner_image_path=partner_image_path,
        status=GenerationStatus.PENDING,
        has_watermark=add_watermark,
        was_free_generation=template.is_free
    )
    
    db.add(generation)
    db.commit()
    db.refresh(generation)
    
    # Deduct credit if not free template
    if not template.is_free:
        current_user.credits_remaining -= 1
        db.commit()
    
    # Update template usage
    template.usage_count += 1
    db.commit()
    
    # Start background generation
    background_tasks.add_task(
        process_generation,
        generation.id,
        user_image_path,
        partner_image_path,
        template.prompt,
        add_watermark,
        db
    )
    
    return generation

@router.get("/", response_model=GenerationListResponse)
async def get_user_generations(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all generations for current user"""
    query = db.query(Generation).filter(Generation.user_id == current_user.id)
    
    generations = query.order_by(Generation.created_at.desc()).offset(skip).limit(limit).all()
    total = query.count()
    
    return {
        "generations": generations,
        "total": total
    }

@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific generation"""
    generation = db.query(Generation).filter(
        Generation.id == generation_id,
        Generation.user_id == current_user.id
    ).first()
    
    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found"
        )
    
    return generation

@router.get("/{generation_id}/status")
async def get_generation_status(
    generation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get generation status for polling"""
    generation = db.query(Generation).filter(
        Generation.id == generation_id,
        Generation.user_id == current_user.id
    ).first()
    
    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found"
        )
    
    return {
        "id": generation.id,
        "status": generation.status,
        "generated_image_url": StorageService.get_file_url(generation.watermarked_image_path or generation.generated_image_path) if generation.status == GenerationStatus.COMPLETED else None,
        "error_message": generation.error_message
    }

@router.delete("/{generation_id}")
async def delete_generation(
    generation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a generation"""
    generation = db.query(Generation).filter(
        Generation.id == generation_id,
        Generation.user_id == current_user.id
    ).first()
    
    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found"
        )
    
    # Delete files
    if generation.user_image_path:
        StorageService.delete_file(generation.user_image_path)
    if generation.partner_image_path:
        StorageService.delete_file(generation.partner_image_path)
    if generation.generated_image_path:
        StorageService.delete_file(generation.generated_image_path)
    if generation.watermarked_image_path:
        StorageService.delete_file(generation.watermarked_image_path)
    
    # Delete record
    db.delete(generation)
    db.commit()
    
    return {"message": "Generation deleted successfully"}