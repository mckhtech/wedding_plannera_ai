from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.generation import Generation, GenerationStatus, GenerationMode
from app.models.payment_token import PaymentToken
from app.services.image_generation_service import ImageGenerationService
from app.services.payment_service import PaymentService
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="process_image_generation")
def process_generation_task(
    self,
    generation_id: int,
    generation_mode: str,
    user_images: Optional[List[str]],
    partner_images: Optional[List[str]],
    couple_image_path: Optional[str],
    prompt: str,
    add_watermark: bool,
):
    """
    Celery task to process image generation
    This runs in a separate worker process
    """
    db_session = SessionLocal()
    generation = None
    
    try:
        logger.info(f"🔄 [Worker {self.request.id}] Processing generation {generation_id}")
        
        # Get generation
        generation = db_session.query(Generation).filter(
            Generation.id == generation_id
        ).first()
        
        if not generation:
            logger.error(f"❌ Generation {generation_id} not found")
            return
        
        # Update status
        generation.status = GenerationStatus.PROCESSING
        db_session.commit()
        
        # Convert string mode back to enum
        mode = GenerationMode(generation_mode)
        
        # Verify files exist
        if mode == GenerationMode.FLEXIBLE:
            for i, path in enumerate(user_images, 1):
                if not Path(path).exists():
                    raise FileNotFoundError(f"User image {i} not found: {path}")
            for i, path in enumerate(partner_images, 1):
                if not Path(path).exists():
                    raise FileNotFoundError(f"Partner image {i} not found: {path}")
        
        elif mode == GenerationMode.COUPLE:
            if not Path(couple_image_path).exists():
                raise FileNotFoundError(f"Couple image not found: {couple_image_path}")
        
        # Generate image (this is async but we run it sync in Celery)
        logger.info(f"   🎨 Starting image generation...")
        image_service = ImageGenerationService()
        
        # Run async function in sync context
        import asyncio
        generated_path, watermarked_path = asyncio.run(
            image_service.generate_image(
                generation_mode=mode,
                user_images=user_images,
                partner_images=partner_images,
                couple_image_path=couple_image_path,
                prompt=prompt,
                add_watermark=add_watermark
            )
        )
        
        logger.info(f"   ✅ Generation complete!")
        
        # Update generation record
        generation.generated_image_path = generated_path
        generation.watermarked_image_path = watermarked_path
        generation.status = GenerationStatus.COMPLETED
        generation.completed_at = datetime.utcnow()
        generation.has_watermark = add_watermark
        
        # Mark payment token as used
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
        
        # Re-raise for Celery retry mechanism
        raise self.retry(exc=e, countdown=60, max_retries=3)
    
    finally:
        db_session.close()