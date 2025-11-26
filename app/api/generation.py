from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models.generation import Generation, GenerationStatus
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

router = APIRouter(prefix="/api/generate", tags=["Image Generation"])
logger = logging.getLogger(__name__)

async def process_generation(
    generation_id: int,
    user_image_path: str,
    partner_image_path: Optional[str],
    prompt: str,
    add_watermark: bool,
):
    """Background task to process image generation"""
    from app.database import SessionLocal
    db_session = SessionLocal()
    generation = None
    
    try:
        logger.info(f"🔄 Processing generation {generation_id}")
        
        # Get generation
        generation = db_session.query(Generation).filter(Generation.id == generation_id).first()
        if not generation:
            logger.error(f"❌ Generation {generation_id} not found")
            return
        
        # Update status
        generation.status = GenerationStatus.PROCESSING
        db_session.commit()
        
        # Verify files exist
        user_path = Path(user_image_path)
        if not user_path.exists():
            raise FileNotFoundError(f"User image not found: {user_image_path}")
        
        if partner_image_path:
            partner_path = Path(partner_image_path)
            if not partner_path.exists():
                raise FileNotFoundError(f"Partner image not found: {partner_image_path}")
        
        # Generate image
        logger.info(f"   Starting image generation...")
        image_service = ImageGenerationService()
        generated_path, watermarked_path = await image_service.generate_image(
            user_image_path,
            partner_image_path,
            prompt,
            add_watermark
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
    template_id: int,
    user_image: UploadFile = File(...),
    partner_image: Optional[UploadFile] = File(None),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new image generation request
    
    Logic:
    - FREE TEMPLATES: Requires 1 free credit (deducted immediately)
    - PAID TEMPLATES: Requires unused payment token (must pay first)
    """
    
    # Get template
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # ============================================
    # ACCESS CONTROL - NEW LOGIC
    # ============================================
    
    payment_token_id = None
    used_free_credit = False
    used_paid_token = False
    
    if template.is_free:
        # FREE TEMPLATE - Need free credit
        if not current_user.can_generate_with_free_template():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_credits",
                    "message": "No free credits remaining. You have used all your free generations.",
                    "free_credits_remaining": current_user.free_credits_remaining,
                    "suggestion": "Purchase credits or try a paid template"
                }
            )
        
        # Deduct free credit BEFORE generation
        if not current_user.deduct_free_credit():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Failed to deduct credit"
            )
        
        used_free_credit = True
        logger.info(f"💳 FREE TEMPLATE: Credit deducted. User {current_user.id} now has {current_user.free_credits_remaining} credits")
        
    else:
        # PAID TEMPLATE - Need paid token
        if not current_user.can_generate_with_paid_template(template_id):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "payment_required",
                    "message": f"Payment required for template: {template.name}",
                    "template_id": template_id,
                    "template_price": float(template.price),
                    "currency": template.currency,
                    "action": "Please complete payment before generating"
                }
            )
        
        # Get unused token
        token = current_user.get_unused_token_for_template(template_id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No valid payment token found"
            )
        
        payment_token_id = token.id
        used_paid_token = True
        logger.info(f"💳 PAID TEMPLATE: Using token {token.id} for user {current_user.id}")
    
    # Commit credit deduction
    db.commit()
    db.refresh(current_user)
    
    # ============================================
    # VALIDATE & SAVE IMAGES
    # ============================================
    
    StorageService.validate_image_file(user_image)
    if partner_image:
        StorageService.validate_image_file(partner_image)
    
    user_image_path = await StorageService.save_upload_file(user_image, "uploads")
    partner_image_path = None
    if partner_image:
        partner_image_path = await StorageService.save_upload_file(partner_image, "uploads")
    
    # Watermark logic: Only for paid templates if user not subscribed
    add_watermark = not template.is_free and not current_user.is_subscribed
    
    # ============================================
    # CREATE GENERATION RECORD
    # ============================================
    
    generation = Generation(
        user_id=current_user.id,
        template_id=template_id,
        payment_token_id=payment_token_id,
        user_image_path=user_image_path,
        partner_image_path=partner_image_path,
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
    
    generation_id = generation.id
    
    background_tasks.add_task(
        process_generation,
        generation_id,
        user_image_path,
        partner_image_path,
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
        "generated_image_url": generated_image_url,
        "error_message": generation.error_message,
        "used_free_credit": generation.used_free_credit,
        "used_paid_token": generation.used_paid_token
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