"""
Add this to your API routes to test Razorpay
Create file: app/api/test_payment.py
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.template import Template
from app.services.payment_service import PaymentService
from app.utils.dependencies import get_current_user
from pydantic import BaseModel
import logging

router = APIRouter(prefix="/api/test", tags=["Testing"])
logger = logging.getLogger(__name__)


# ============================================
# TEST SCHEMAS
# ============================================

class TestPaymentFlowRequest(BaseModel):
    template_id: int
    
class ManualVerifyRequest(BaseModel):
    payment_id: str
    token_id: int
    order_id: str


# ============================================
# TEST ENDPOINTS
# ============================================

@router.get("/razorpay/credentials")
async def test_razorpay_credentials():
    """
    Test if Razorpay credentials are valid
    No authentication required - just checks API keys
    """
    result = PaymentService.verify_credentials()
    
    if not result["valid"]:
        raise HTTPException(status_code=400, detail=result)
    
    return result


@router.post("/payment/full-flow")
async def test_full_payment_flow(
    request: TestPaymentFlowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test complete payment flow in TEST MODE
    Steps:
    1. Create payment order
    2. Auto-verify (TEST MODE)
    3. Check token status
    """
    
    # Get template
    template = db.query(Template).filter(
        Template.id == request.template_id,
        Template.is_free == False
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Paid template not found")
    
    try:
        # Step 1: Create order
        logger.info("📝 Step 1: Creating payment order...")
        order_result = PaymentService.create_payment_order(current_user, template, db)
        logger.info(f"✅ Order created: {order_result}")
        
        # Step 2: Verify payment (auto in TEST MODE)
        logger.info("🔐 Step 2: Verifying payment...")
        verify_success = PaymentService.verify_payment(
            order_result['payment_id'],
            order_result['token_id'],
            db
        )
        logger.info(f"✅ Verification: {verify_success}")
        
        # Step 3: Check token
        from app.models.payment_token import PaymentToken
        token = db.query(PaymentToken).filter(
            PaymentToken.id == order_result['token_id']
        ).first()
        
        return {
            "success": True,
            "test_mode": order_result.get('test_mode', True),
            "order": order_result,
            "verification": {
                "verified": verify_success,
                "token_status": token.status.value,
                "payment_status": token.payment_status.value,
                "can_generate": token.status.value == "unused"
            },
            "message": "✅ Full payment flow test completed successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment/create-order-only")
async def test_create_order(
    request: TestPaymentFlowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test ONLY order creation (useful for testing Razorpay API)
    """
    
    template = db.query(Template).filter(
        Template.id == request.template_id,
        Template.is_free == False
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Paid template not found")
    
    try:
        order_result = PaymentService.create_payment_order(current_user, template, db)
        
        return {
            "success": True,
            "order": order_result,
            "next_steps": "Use this order_id to complete payment on Razorpay checkout"
        }
        
    except Exception as e:
        logger.error(f"❌ Order creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment/verify-manual")
async def test_manual_verification(
    request: ManualVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually verify a payment (useful if you complete payment via Razorpay dashboard)
    """
    
    try:
        success = PaymentService.verify_payment(
            request.payment_id,
            request.token_id,
            db,
            order_id=request.order_id
        )
        
        from app.models.payment_token import PaymentToken
        token = db.query(PaymentToken).filter(
            PaymentToken.id == request.token_id
        ).first()
        
        return {
            "verified": success,
            "token_status": token.status.value if token else "not_found",
            "payment_status": token.payment_status.value if token else "not_found"
        }
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payment/my-test-tokens")
async def get_test_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all payment tokens created during testing
    """
    from app.models.payment_token import PaymentToken
    
    tokens = db.query(PaymentToken).filter(
        PaymentToken.user_id == current_user.id
    ).order_by(PaymentToken.created_at.desc()).all()
    
    return {
        "total_tokens": len(tokens),
        "tokens": [
            {
                "token_id": t.id,
                "template_id": t.template_id,
                "amount": float(t.amount_paid),
                "status": t.status.value,
                "payment_status": t.payment_status.value,
                "payment_id": t.payment_id,
                "created_at": t.created_at.isoformat(),
                "can_use": t.status.value == "unused" and t.payment_status.value == "completed"
            }
            for t in tokens
        ]
    }