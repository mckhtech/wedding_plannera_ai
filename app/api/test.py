from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.template import Template
from app.models.generation import Generation
from app.models.payment_token import PaymentToken, TokenStatus, PaymentStatus
from app.utils.dependencies import get_current_user
from app.services.payment_service import PaymentService
import logging

router = APIRouter(prefix="/api/test", tags=["Testing"])
logger = logging.getLogger(__name__)

@router.get("/my-credits")
async def get_my_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check current user's credit balance and tokens"""
    
    # Get unused tokens
    unused_tokens = db.query(PaymentToken).filter(
        PaymentToken.user_id == current_user.id,
        PaymentToken.status == TokenStatus.UNUSED,
        PaymentToken.payment_status == PaymentStatus.COMPLETED
    ).all()
    
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "free_credits_remaining": current_user.free_credits_remaining,
        "is_subscribed": current_user.is_subscribed,
        "unused_paid_tokens": len(unused_tokens),
        "tokens": [
            {
                "token_id": t.id,
                "template_id": t.template_id,
                "amount": float(t.amount_paid)
            } for t in unused_tokens
        ]
    }

@router.post("/check-generation-access/{template_id}")
async def check_generation_access(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test if user can generate with a specific template
    Shows detailed breakdown of access logic
    """
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        return {"error": "Template not found"}
    
    result = {
        "template_id": template_id,
        "template_name": template.name,
        "is_free_template": template.is_free,
        "user_free_credits": current_user.free_credits_remaining,
        "can_generate": False,
        "reason": ""
    }
    
    if template.is_free:
        # FREE TEMPLATE - Need free credit
        if current_user.can_generate_with_free_template():
            result["can_generate"] = True
            result["reason"] = f"✅ Can generate. Will use 1 free credit (current: {current_user.free_credits_remaining})"
        else:
            result["can_generate"] = False
            result["reason"] = "❌ No free credits remaining"
    else:
        # PAID TEMPLATE - Need token
        if current_user.can_generate_with_paid_template(template_id):
            token = current_user.get_unused_token_for_template(template_id)
            result["can_generate"] = True
            result["reason"] = f"✅ Can generate. Will use paid token {token.id}"
            result["token_id"] = token.id
        else:
            result["can_generate"] = False
            result["reason"] = "❌ No paid token available. Must purchase first."
            result["template_price"] = float(template.price)
            result["currency"] = template.currency
    
    return result

@router.post("/simulate-purchase/{template_id}")
async def simulate_purchase(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Simulate purchasing a paid template token (TEST MODE ONLY)
    This creates a completed payment token without actual payment
    """
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        return {"error": "Template not found"}
    
    if template.is_free:
        return {"error": "Cannot purchase free template"}
    
    try:
        # Create payment order (auto-completes in test mode)
        order_data = PaymentService.create_payment_order(current_user, template, db)
        
        return {
            "success": True,
            "message": "✅ Test purchase completed",
            "token_id": order_data["token_id"],
            "payment_id": order_data["payment_id"],
            "amount": order_data["amount"],
            "can_now_generate": True,
            "note": "This is a TEST MODE purchase. In production, user would go through payment gateway."
        }
    except Exception as e:
        return {"error": str(e)}

@router.post("/reset-credits")
async def reset_my_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset your free credits back to 2 for testing"""
    old_credits = current_user.free_credits_remaining
    current_user.free_credits_remaining = 2
    db.commit()
    
    return {
        "message": "Credits reset for testing",
        "old_credits": old_credits,
        "new_credits": 2
    }

@router.get("/generation-history")
async def get_generation_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check all generations and credit usage"""
    
    generations = db.query(Generation).filter(
        Generation.user_id == current_user.id
    ).order_by(Generation.created_at.desc()).limit(20).all()
    
    history = []
    for gen in generations:
        template = db.query(Template).filter(Template.id == gen.template_id).first()
        
        credit_info = "Unknown"
        if gen.used_free_credit:
            credit_info = "Used FREE credit"
        elif gen.used_paid_token:
            credit_info = f"Used PAID token (#{gen.payment_token_id})"
        
        history.append({
            "id": gen.id,
            "template_name": template.name if template else "Unknown",
            "is_free_template": template.is_free if template else None,
            "credit_used": credit_info,
            "status": gen.status.value,
            "created_at": gen.created_at.isoformat()
        })
    
    return {
        "current_free_credits": current_user.free_credits_remaining,
        "total_generations": len(generations),
        "generation_history": history
    }

@router.delete("/delete-all-tokens")
async def delete_all_my_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete all payment tokens for testing
    WARNING: This will delete your purchase history!
    """
    
    tokens = db.query(PaymentToken).filter(
        PaymentToken.user_id == current_user.id
    ).all()
    
    count = len(tokens)
    
    for token in tokens:
        db.delete(token)
    
    db.commit()
    
    return {
        "message": f"Deleted {count} payment tokens",
        "warning": "This is for testing only!"
    }

@router.get("/template-prices")
async def get_template_prices(
    db: Session = Depends(get_db)
):
    """Show all templates with their prices"""
    
    templates = db.query(Template).filter(Template.is_active == True).all()
    
    template_list = []
    for t in templates:
        template_list.append({
            "id": t.id,
            "name": t.name,
            "is_free": t.is_free,
            "price": float(t.price) if t.price else 0,
            "currency": t.currency,
            "usage_count": t.usage_count
        })
    
    return {
        "templates": template_list,
        "total": len(template_list),
        "free_count": len([t for t in template_list if t["is_free"]]),
        "paid_count": len([t for t in template_list if not t["is_free"]])
    }