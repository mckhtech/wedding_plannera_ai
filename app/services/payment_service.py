"""
Payment Service - Handles payment processing for paid templates

For Testing: Set PAYMENT_TEST_MODE=True to bypass actual payment gateway
For Production: Set PAYMENT_TEST_MODE=False to use real Razorpay
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.payment_token import PaymentToken, PaymentStatus, TokenStatus
from app.models.user import User
from app.models.template import Template
from datetime import datetime, timedelta
import secrets

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================
PAYMENT_TEST_MODE = True  # Set to False for production with real payment gateway

class PaymentService:
    
    @staticmethod
    def create_payment_order(
        user: User,
        template: Template,
        db: Session
    ) -> Dict[str, Any]:
        """
        Create a payment order for a template generation
        
        Returns payment order details that frontend will use
        """
        
        if template.is_free:
            raise ValueError("Cannot create payment for free template")
        
        # Create payment token record
        token = PaymentToken(
            user_id=user.id,
            template_id=template.id,
            payment_status=PaymentStatus.PENDING,
            amount_paid=template.price,
            currency=template.currency,
            status=TokenStatus.UNUSED
        )
        
        db.add(token)
        db.commit()
        db.refresh(token)
        
        # ============================================
        # TEST MODE - Skip real payment
        # ============================================
        if PAYMENT_TEST_MODE:
            logger.info(f"🧪 TEST MODE: Auto-completing payment for token {token.id}")
            
            # Simulate successful payment
            token.payment_id = f"TEST_PAY_{secrets.token_hex(8)}"
            token.payment_status = PaymentStatus.COMPLETED
            db.commit()
            
            return {
                "token_id": token.id,
                "payment_id": token.payment_id,
                "amount": float(token.amount_paid),
                "currency": token.currency,
                "status": "completed",
                "test_mode": True,
                "message": "Test payment auto-completed"
            }
        
        # ============================================
        # PRODUCTION MODE - Real Payment Gateway
        # ============================================
        
        try:
            import razorpay
            from app.config import settings
            
            # Initialize Razorpay client
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            # Create order
            order_data = {
                "amount": int(template.price * 100),  # Amount in paise (smallest currency unit)
                "currency": template.currency,
                "receipt": f"token_{token.id}",
                "notes": {
                    "user_id": user.id,
                    "template_id": template.id,
                    "token_id": token.id,
                    "user_email": user.email
                }
            }
            
            logger.info(f"📝 Creating Razorpay order: {order_data}")
            order = client.order.create(data=order_data)
            logger.info(f"✅ Razorpay order created: {order['id']}")
            
            # Save order ID
            token.payment_id = order['id']
            db.commit()
            
            return {
                "token_id": token.id,
                "order_id": order['id'],
                "amount": float(template.price),
                "currency": template.currency,
                "status": "pending",
                "razorpay_key": settings.RAZORPAY_KEY_ID,
                "test_mode": False
            }
            
        except Exception as e:
            logger.error(f"❌ Payment order creation failed: {str(e)}")
            token.payment_status = PaymentStatus.FAILED
            db.commit()
            raise Exception(f"Failed to create Razorpay order: {str(e)}")
    
    @staticmethod
    def verify_payment(
        payment_id: str,
        token_id: int,
        db: Session,
        razorpay_signature: Optional[str] = None,
        order_id: Optional[str] = None
    ) -> bool:
        """
        Verify payment completion
        
        For TEST MODE: Always returns True
        For PRODUCTION: Verifies with payment gateway
        """
        
        token = db.query(PaymentToken).filter(PaymentToken.id == token_id).first()
        if not token:
            raise ValueError("Payment token not found")
        
        # ============================================
        # TEST MODE - Auto verify
        # ============================================
        if PAYMENT_TEST_MODE:
            logger.info(f"🧪 TEST MODE: Auto-verifying payment {payment_id}")
            token.payment_status = PaymentStatus.COMPLETED
            if not token.payment_id:
                token.payment_id = payment_id
            db.commit()
            return True
        
        # ============================================
        # PRODUCTION MODE - Verify with gateway
        # ============================================
        
        try:
            import razorpay
            from app.config import settings
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            # Get order_id from token if not provided
            if not order_id:
                order_id = token.payment_id
            
            if not order_id:
                raise ValueError("Order ID not found")
            
            # Verify signature
            if razorpay_signature:
                params_dict = {
                    'razorpay_payment_id': payment_id,
                    'razorpay_order_id': order_id,
                    'razorpay_signature': razorpay_signature
                }
                
                logger.info(f"🔐 Verifying Razorpay signature...")
                client.utility.verify_payment_signature(params_dict)
                logger.info(f"✅ Signature verified successfully")
            
            # Fetch payment details to confirm
            payment = client.payment.fetch(payment_id)
            
            if payment['status'] == 'captured' or payment['status'] == 'authorized':
                token.payment_status = PaymentStatus.COMPLETED
                token.payment_id = payment_id  # Update with actual payment ID
                db.commit()
                logger.info(f"✅ Payment verified: {payment_id}")
                return True
            else:
                logger.warning(f"⚠️ Payment not captured: {payment['status']}")
                return False
            
        except razorpay.errors.SignatureVerificationError as e:
            logger.error(f"❌ Signature verification failed: {str(e)}")
            token.payment_status = PaymentStatus.FAILED
            db.commit()
            return False
        except Exception as e:
            logger.error(f"❌ Payment verification failed: {str(e)}")
            token.payment_status = PaymentStatus.FAILED
            db.commit()
            return False
    
    @staticmethod
    def refund_payment(
        token_id: int,
        reason: str,
        db: Session
    ) -> bool:
        """
        Refund a payment (e.g., if generation fails)
        """
        
        token = db.query(PaymentToken).filter(PaymentToken.id == token_id).first()
        if not token:
            raise ValueError("Payment token not found")
        
        if token.payment_status != PaymentStatus.COMPLETED:
            raise ValueError("Cannot refund non-completed payment")
        
        # ============================================
        # TEST MODE - Auto refund
        # ============================================
        if PAYMENT_TEST_MODE:
            logger.info(f"🧪 TEST MODE: Auto-refunding payment token {token_id}")
            refund_id = f"TEST_REFUND_{secrets.token_hex(8)}"
            token.mark_as_refunded(refund_id, reason)
            db.commit()
            return True
        
        # ============================================
        # PRODUCTION MODE - Process actual refund
        # ============================================
        
        try:
            import razorpay
            from app.config import settings
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            # Create refund
            logger.info(f"💰 Processing refund for payment: {token.payment_id}")
            refund = client.payment.refund(token.payment_id, {
                "amount": int(token.amount_paid * 100),  # Amount in paise
                "notes": {"reason": reason}
            })
            
            logger.info(f"✅ Refund processed: {refund['id']}")
            token.mark_as_refunded(refund['id'], reason)
            db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Refund failed: {str(e)}")
            return False
    
    @staticmethod
    def verify_credentials() -> Dict[str, Any]:
        """
        Test Razorpay credentials by fetching account details
        """
        try:
            import razorpay
            from app.config import settings
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            # Try to fetch orders (will fail if credentials are invalid)
            orders = client.order.all({'count': 1})
            
            return {
                "valid": True,
                "message": "Razorpay credentials are valid",
                "test_mode": settings.RAZORPAY_KEY_ID.startswith('rzp_test_')
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"Razorpay credentials invalid: {str(e)}",
                "error": str(e)
            }