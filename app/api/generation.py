from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Request, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from app.database import get_db
from app.models.generation import Generation, GenerationStatus, GenerationMode
from app.models.template import Template
from app.models.user import User
from app.models.payment_token import PaymentToken, TokenStatus
from app.schemas.generation import GenerationResponse, GenerationListResponse
from app.utils.dependencies import get_current_user
from app.services.storage_service import StorageService
from app.services.image_generation_service import ImageGenerationService
from app.services.payment_service import PaymentService
from pathlib import Path
import logging
import json

router = APIRouter(prefix="/api/generate", tags=["Image Generation"])
logger = logging.getLogger(__name__)

async def process_generation(
    generation_id: int,
    generation_mode: GenerationMode,
    user_image_path: Optional[str],
    partner_image_path: Optional[str],
    couple_image_path: Optional[str],
    user_images: Optional[dict],
    partner_images: Optional[dict],
    prompt: str,
    add_watermark: bool,
):
    """Background task to process image generation"""
    from app.database import SessionLocal
    db_session = SessionLocal()
    generation = None
    
    try:
        logger.info(f"🔄 Processing generation {generation_id} - Mode: {generation_mode}")
        
        # Get generation
        generation = db_session.query(Generation).filter(Generation.id == generation_id).first()
        if not generation:
            logger.error(f"❌ Generation {generation_id} not found")
            return
        
        # Update status
        generation.status = GenerationStatus.PROCESSING
        db_session.commit()
        
        # Verify files exist based on mode
        if generation_mode == GenerationMode.SINGLE:
            if not Path(user_image_path).exists():
                raise FileNotFoundError(f"User image not found: {user_image_path}")
            if partner_image_path and not Path(partner_image_path).exists():
                raise FileNotFoundError(f"Partner image not found: {partner_image_path}")
        
        elif generation_mode == GenerationMode.COUPLE:
            if not Path(couple_image_path).exists():
                raise FileNotFoundError(f"Couple image not found: {couple_image_path}")
        
        elif generation_mode == GenerationMode.MULTI_ANGLE:
            for angle, path in user_images.items():
                if not Path(path).exists():
                    raise FileNotFoundError(f"User {angle} image not found: {path}")
            for angle, path in partner_images.items():
                if not Path(path).exists():
                    raise FileNotFoundError(f"Partner {angle} image not found: {path}")
        
        # Generate image
        logger.info(f"   Starting image generation...")
        image_service = ImageGenerationService()
        generated_path, watermarked_path = await image_service.generate_image(
            generation_mode=generation_mode,
            user_image_path=user_image_path,
            partner_image_path=partner_image_path,
            couple_image_path=couple_image_path,
            user_images=user_images,
            partner_images=partner_images,
            prompt=prompt,
            add_watermark=add_watermark
        )
        
        logger.info(f"   ✅ Generation complete!")
        
        # Update generation record
        generation.generated_image_path = generated_path
        generation.watermarked_image_path = watermarked_path
        generation.status = GenerationStatus.COMPLETED
        generation.completed_at = datetime.utcnow()
        generation.has_watermark = add_watermark
        
        # Mark payment token as used (if paid generation)
        if generation.payment_token_id:
            token = db_session.query(PaymentToken).filter(
                PaymentToken.id == generation.payment_token_id
            ).first()
            if token:
                token.mark_as_used()
        
        db_session.commit()
        logger.info(f"✅ Generation {generation_id} completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Generation {generation_id} failed: {str(e)}")
        logger.exception("Full traceback:")
        
        # Update with error
        if generation:
            generation.status = GenerationStatus.FAILED
            generation.error_message = str(e)
            db_session.commit()
            
            # REFUND if paid generation failed
            if generation.payment_token_id:
                try:
                    PaymentService.refund_payment(
                        generation.payment_token_id,
                        f"Generation failed: {str(e)}",
                        db_session
                    )
                    logger.info(f"   💰 Payment refunded for failed generation")
                except Exception as refund_error:
                    logger.error(f"   ❌ Refund failed: {str(refund_error)}")
    
    finally:
        db_session.close()


@router.post("/", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
async def create_generation(
    request: Request,
    template_id: int = Form(...),
    generation_mode: str = Form(...),  # "single", "couple", "multi_angle"
    
    # Mode 1: SINGLE
    user_image: Optional[UploadFile] = File(None),
    partner_image: Optional[UploadFile] = File(None),
    
    # Mode 2: COUPLE
    couple_image: Optional[UploadFile] = File(None),
    
    # Mode 3: MULTI_ANGLE
    user_front: Optional[UploadFile] = File(None),
    user_left_side: Optional[UploadFile] = File(None),
    user_right_side: Optional[UploadFile] = File(None),
    partner_front: Optional[UploadFile] = File(None),
    partner_left_side: Optional[UploadFile] = File(None),
    partner_right_side: Optional[UploadFile] = File(None),
    
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new image generation request with support for 3 modes:
    
    - SINGLE: 1 user image + optional partner image
    - COUPLE: 1 image with both people together
    - MULTI_ANGLE: 3 user images + 3 partner images (front, left_side, right_side)
    """
    
    # Validate generation mode
    try:
        mode = GenerationMode(generation_mode.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid generation mode. Must be: single, couple, or multi_angle"
        )
    
    # Get template
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # ============================================
    # ACCESS CONTROL
    # ============================================
    payment_token_id = None
    used_free_credit = False
    used_paid_token = False
    
    if template.is_free:
        if not current_user.can_generate_with_free_template():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_credits",
                    "message": "No free credits remaining.",
                    "free_credits_remaining": current_user.free_credits_remaining
                }
            )
        
        if not current_user.deduct_free_credit():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Failed to deduct credit"
            )
        
        used_free_credit = True
        logger.info(f"💳 FREE: Credit deducted. User {current_user.id} has {current_user.free_credits_remaining} credits")
        
    else:
        if not current_user.can_generate_with_paid_template(template_id):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "payment_required",
                    "message": f"Payment required for template: {template.name}",
                    "template_price": float(template.price)
                }
            )
        
        token = current_user.get_unused_token_for_template(template_id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No valid payment token found"
            )
        
        payment_token_id = token.id
        used_paid_token = True
        logger.info(f"💳 PAID: Using token {token.id}")
    
    db.commit()
    db.refresh(current_user)
    
    # ============================================
    # VALIDATE & SAVE IMAGES BASED ON MODE
    # ============================================
    
    user_image_path = None
    partner_image_path = None
    couple_image_path = None
    user_images_dict = None
    partner_images_dict = None
    
    if mode == GenerationMode.SINGLE:
        # Validate: Must have user_image
        if not user_image:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_image is required for SINGLE mode"
            )
        
        StorageService.validate_image_file(user_image)
        user_image_path = await StorageService.save_upload_file(user_image, "uploads")
        
        if partner_image:
            StorageService.validate_image_file(partner_image)
            partner_image_path = await StorageService.save_upload_file(partner_image, "uploads")
    
    elif mode == GenerationMode.COUPLE:
        # Validate: Must have couple_image
        if not couple_image:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="couple_image is required for COUPLE mode"
            )
        
        StorageService.validate_image_file(couple_image)
        couple_image_path = await StorageService.save_upload_file(couple_image, "uploads")
    
    elif mode == GenerationMode.MULTI_ANGLE:
        # Validate: Must have all 6 images
        required_files = {
            "user_front": user_front,
            "user_left_side": user_left_side,
            "user_right_side": user_right_side,
            "partner_front": partner_front,
            "partner_left_side": partner_left_side,
            "partner_right_side": partner_right_side
        }
        
        missing = [name for name, file in required_files.items() if not file]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required images for MULTI_ANGLE mode: {', '.join(missing)}"
            )
        
        # Save user images
        user_images_dict = {}
        for angle, file in [("front", user_front), ("left_side", user_left_side), ("right_side", user_right_side)]:
            StorageService.validate_image_file(file)
            path = await StorageService.save_upload_file(file, "uploads")
            user_images_dict[angle] = path
        
        # Save partner images
        partner_images_dict = {}
        for angle, file in [("front", partner_front), ("left_side", partner_left_side), ("right_side", partner_right_side)]:
            StorageService.validate_image_file(file)
            path = await StorageService.save_upload_file(file, "uploads")
            partner_images_dict[angle] = path
    
    # Watermark logic
    add_watermark = not template.is_free and not current_user.is_subscribed
    
    # ============================================
    # CREATE GENERATION RECORD
    # ============================================
    
    generation = Generation(
        user_id=current_user.id,
        template_id=template_id,
        payment_token_id=payment_token_id,
        generation_mode=mode,
        
        # Mode 1
        user_image_path=user_image_path,
        partner_image_path=partner_image_path,
        
        # Mode 2
        couple_image_path=couple_image_path,
        
        # Mode 3
        user_images=user_images_dict,
        partner_images=partner_images_dict,
        
        status=GenerationStatus.PENDING,
        has_watermark=add_watermark,
        used_free_credit=used_free_credit,
        used_paid_token=used_paid_token
    )
    
    db.add(generation)
    db.commit()
    db.refresh(generation)
    
    # Update template usage
    template.usage_count += 1
    db.commit()
    
    # ============================================
    # START BACKGROUND GENERATION
    # ============================================
    
    background_tasks.add_task(
        process_generation,
        generation.id,
        mode,
        user_image_path,
        partner_image_path,
        couple_image_path,
        user_images_dict,
        partner_images_dict,
        template.prompt,
        add_watermark
    )
    
    # Return response
    response = GenerationResponse.model_validate(generation)
    response._request = request
    return response


@router.get("/", response_model=GenerationListResponse)
async def get_user_generations(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all generations for current user"""
    query = db.query(Generation).filter(Generation.user_id == current_user.id)
    
    generations = query.order_by(Generation.created_at.desc()).offset(skip).limit(limit).all()
    total = query.count()
    
    generation_responses = []
    for gen in generations:
        response = GenerationResponse.model_validate(gen)
        response._request = request
        generation_responses.append(response)
    
    return {
        "generations": generation_responses,
        "total": total
    }


@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    request: Request,
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
    
    response = GenerationResponse.model_validate(generation)
    response._request = request
    return response


@router.get("/{generation_id}/status")
async def get_generation_status(
    request: Request,
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
    
    generated_image_url = None
    if generation.status == GenerationStatus.COMPLETED:
        image_path = generation.watermarked_image_path or generation.generated_image_path
        generated_image_url = StorageService.get_file_url(image_path, request)
    
    return {
        "id": generation.id,
        "status": generation.status,
        "generation_mode": generation.generation_mode,
        "generated_image_url": generated_image_url,
        "error_message": generation.error_message,
        "used_free_credit": generation.used_free_credit,
        "used_paid_token": generation.used_paid_token
    }


@router.get("/{generation_id}/download")
async def download_generation(
    generation_id: int,
    include_watermark: bool = True,  # Default: download watermarked if available
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download generated image
    
    Args:
        generation_id: ID of the generation
        include_watermark: If True and watermark exists, download watermarked version
                          If False, download original generated image
    
    Returns:
        FileResponse: Direct file download
    """
    # Get generation
    generation = db.query(Generation).filter(
        Generation.id == generation_id,
        Generation.user_id == current_user.id
    ).first()
    
    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found"
        )
    
    # Check if generation is completed
    if generation.status != GenerationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Generation is not completed yet. Current status: {generation.status}"
        )
    
    # Determine which image to download
    if include_watermark and generation.watermarked_image_path:
        file_path = generation.watermarked_image_path
        filename_suffix = "_watermarked"
    elif generation.generated_image_path:
        file_path = generation.generated_image_path
        filename_suffix = ""
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated image not found"
        )
    
    # Verify file exists
    if not StorageService.file_exists(file_path):
        logger.error(f"File not found on disk: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found on server"
        )
    
    # Get template for filename
    template = db.query(Template).filter(Template.id == generation.template_id).first()
    template_name = template.name.replace(" ", "_") if template else "template"
    
    # Create download filename
    file_extension = Path(file_path).suffix
    download_filename = f"{template_name}_generation_{generation.id}{filename_suffix}{file_extension}"
    
    logger.info(f"📥 User {current_user.id} downloading generation {generation.id}: {download_filename}")
    
    # Return file
    return FileResponse(
        path=file_path,
        filename=download_filename,
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename={download_filename}"
        }
    )


@router.delete("/{generation_id}")
async def delete_generation(
    generation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a generation and all associated files"""
    generation = db.query(Generation).filter(
        Generation.id == generation_id,
        Generation.user_id == current_user.id
    ).first()
    
    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found"
        )
    
    # Delete all input files based on mode
    for path in generation.get_all_input_image_paths():
        StorageService.delete_file(path)
    
    # Delete output files
    if generation.generated_image_path:
        StorageService.delete_file(generation.generated_image_path)
    if generation.watermarked_image_path:
        StorageService.delete_file(generation.watermarked_image_path)
    
    # Delete record
    db.delete(generation)
    db.commit()
    
    return {"message": "Generation deleted successfully"}