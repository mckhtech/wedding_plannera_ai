from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.models.template import Template
from app.models.payment_token import PaymentToken, PaymentStatus, TokenStatus
from app.utils.dependencies import get_current_user
from app.services.payment_service import PaymentService
from pydantic import BaseModel
import logging

router = APIRouter(prefix="/api/payment", tags=["Payment"])
logger = logging.getLogger(__name__)


class PaymentOrderRequest(BaseModel):
    template_id: int

class PaymentOrderResponse(BaseModel):
    token_id: int
    payment_id: Optional[str]
    order_id: Optional[str] = None
    amount: float
    currency: str
    status: str
    test_mode: bool = False
    message: Optional[str] = None
    razorpay_key: Optional[str] = None

class PaymentVerifyRequest(BaseModel):
    payment_id: str
    token_id: int
    razorpay_signature: Optional[str] = None

class TokenListResponse(BaseModel):
    token_id: int
    template_id: int
    template_name: str
    amount_paid: float
    currency: str
    status: str
    payment_status: str
    created_at: str
    used_at: Optional[str]


@router.post("/create-order", response_model=PaymentOrderResponse)
async def create_payment_order(
    request: PaymentOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a payment order for a paid template
    
    Flow:
    1. User selects paid template
    2. This endpoint creates payment order
    3. Frontend shows payment gateway
    4. After payment, call /verify endpoint
    5. Then user can generate image
    """
    
    # Get template
    template = db.query(Template).filter(Template.id == request.template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Check if template is paid
    if template.is_free:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create payment order for free template"
        )
    
    # Check if template has price set
    if not template.price or template.price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template price not configured"
        )
    
    # Create payment order
    try:
        order_data = PaymentService.create_payment_order(current_user, template, db)
        
        logger.info(f"💳 Payment order created: Token {order_data['token_id']} for user {current_user.id}")
        
        return PaymentOrderResponse(**order_data)
        
    except Exception as e:
        logger.error(f"Payment order creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create payment order: {str(e)}"
        )


@router.post("/verify")
async def verify_payment(
    request: PaymentVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify payment completion
    
    Called by frontend after payment gateway confirms payment
    """
    
    # Get token
    token = db.query(PaymentToken).filter(
        PaymentToken.id == request.token_id,
        PaymentToken.user_id == current_user.id
    ).first()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment token not found"
        )
    
    # Verify payment
    try:
        success = PaymentService.verify_payment(
            request.payment_id,
            request.token_id,
            db,
            request.razorpay_signature
        )
        
        if success:
            logger.info(f"✅ Payment verified: Token {token.id}")
            return {
                "success": True,
                "message": "Payment verified successfully",
                "token_id": token.id,
                "can_generate": True
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment verification failed"
            )
            
    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment verification failed: {str(e)}"
        )


@router.get("/my-tokens")
async def get_my_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all payment tokens for current user
    Shows purchase history and unused tokens
    """
    
    tokens = db.query(PaymentToken).filter(
        PaymentToken.user_id == current_user.id
    ).order_by(PaymentToken.created_at.desc()).all()
    
    token_list = []
    for token in tokens:
        template = db.query(Template).filter(Template.id == token.template_id).first()
        token_list.append({
            "token_id": token.id,
            "template_id": token.template_id,
            "template_name": template.name if template else "Unknown",
            "amount_paid": float(token.amount_paid),
            "currency": token.currency,
            "status": token.status.value,
            "payment_status": token.payment_status.value,
            "created_at": token.created_at.isoformat(),
            "used_at": token.used_at.isoformat() if token.used_at else None,
            "can_use": token.status == TokenStatus.UNUSED and token.payment_status == PaymentStatus.COMPLETED
        })
    
    return {
        "tokens": token_list,
        "total": len(token_list),
        "unused_tokens": len([t for t in token_list if t["can_use"]])
    }


@router.get("/check-access/{template_id}")
async def check_template_access(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if user can generate with a specific template
    Returns what's needed to proceed
    """
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    response = {
        "template_id": template_id,
        "template_name": template.name,
        "is_free_template": template.is_free,
        "can_generate": False,
        "reason": "",
        "action_required": ""
    }
    
    if template.is_free:
        # FREE TEMPLATE
        if current_user.can_generate_with_free_template():
            response["can_generate"] = True
            response["reason"] = f"You have {current_user.free_credits_remaining} free credits remaining"
            response["free_credits_remaining"] = current_user.free_credits_remaining
        else:
            response["can_generate"] = False
            response["reason"] = "No free credits remaining"
            response["action_required"] = "All free credits used. Purchase a paid template to continue."
            response["free_credits_remaining"] = 0
    else:
        # PAID TEMPLATE
        if current_user.can_generate_with_paid_template(template_id):
            response["can_generate"] = True
            response["reason"] = "Valid payment token available"
        else:
            response["can_generate"] = False
            response["reason"] = "Payment required"
            response["action_required"] = "purchase"
            response["price"] = float(template.price)
            response["currency"] = template.currency
    
    return response