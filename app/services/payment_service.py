"""
Payment Service - Handles payment processing for paid templates

Configuration via environment variables:
- PAYMENT_TEST_MODE: Set to "true" for test mode, "false" for production
- RAZORPAY_KEY_ID: Razorpay API key ID
- RAZORPAY_KEY_SECRET: Razorpay API secret
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.payment_token import PaymentToken, PaymentStatus, TokenStatus
from app.models.user import User
from app.models.template import Template
import secrets
import hmac
import hashlib
from app.config import settings

logger = logging.getLogger(__name__)

class PaymentService:
    
    @staticmethod
    def _is_test_mode() -> bool:
        """Check if payment service is in test mode"""
        return getattr(settings, 'PAYMENT_TEST_MODE', False)
    
    @staticmethod
    def create_payment_order(
        user: User,
        template: Template,
        db: Session
    ) -> Dict[str, Any]:
        """
        Create a payment order for a template generation
        
        Args:
            user: User making the payment
            template: Template being purchased
            db: Database session
            
        Returns:
            Dict containing payment order details
            
        Raises:
            ValueError: If template is free
            Exception: If order creation fails
        """
        
        if template.is_free:
            logger.error(f"Attempted to create payment for free template {template.id}")
            raise ValueError("Cannot create payment for free template")
        
        try:
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
            
            logger.info(f"Payment token created: {token.id} for user {user.id}, template {template.id}")
            
            # TEST MODE
            if PaymentService._is_test_mode():
                logger.info(f"TEST MODE: Creating test order for token {token.id}")
                
                # Generate test order ID (not payment ID yet)
                test_order_id = f"order_TEST_{secrets.token_hex(8)}"
                token.payment_id = test_order_id  # Store order ID temporarily
                db.commit()
                
                return {
                    "token_id": token.id,
                    "payment_id": None,
                    "order_id": test_order_id,
                    "amount": float(token.amount_paid),
                    "currency": token.currency,
                    "status": "pending",
                    "test_mode": True,
                    "message": "Test mode: Use any payment_id to verify",
                    "razorpay_key": "rzp_test_TESTMODE"
                }
            
            # PRODUCTION MODE
            import razorpay
            
            if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
                logger.error("Razorpay credentials not configured")
                raise Exception("Payment gateway not configured")
            
            # Initialize Razorpay client
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            # Create order
            order_data = {
                "amount": int(template.price * 100),  # Convert to smallest currency unit
                "currency": template.currency,
                "receipt": f"token_{token.id}",
                "notes": {
                    "user_id": str(user.id),
                    "template_id": str(template.id),
                    "token_id": str(token.id),
                    "user_email": user.email
                }
            }
            
            logger.info(f"Creating Razorpay order for token {token.id}")
            order = client.order.create(data=order_data)
            logger.info(f"Razorpay order created: {order['id']}")
            
            # Save order ID (not payment ID yet)
            token.payment_id = order['id']
            db.commit()
            
            return {
                "token_id": token.id,
                "payment_id": None,
                "order_id": order['id'],
                "amount": float(template.price),
                "currency": template.currency,
                "status": "pending",
                "razorpay_key": settings.RAZORPAY_KEY_ID,
                "test_mode": False
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Payment order creation failed: {str(e)}", exc_info=True)
            
            # Mark token as failed if it exists
            if 'token' in locals():
                token.payment_status = PaymentStatus.FAILED
                db.commit()
            
            raise Exception(f"Failed to create payment order: {str(e)}")
    

    @staticmethod
    def verify_payment(
        payment_id: str,
        order_id: str,
        token_id: int,
        db: Session,
        razorpay_signature: Optional[str] = None
    ) -> bool:
        """
        Verify payment completion
        
        Args:
            payment_id: Razorpay payment ID (e.g., pay_xxxxx)
            order_id: Razorpay order ID (e.g., order_xxxxx)
            token_id: Payment token ID
            db: Database session
            razorpay_signature: Razorpay signature for verification
            
        Returns:
            bool: True if verification successful
        """
        
        # Get token
        token = db.query(PaymentToken).filter(PaymentToken.id == token_id).first()
        if not token:
            logger.error(f"Payment token not found: {token_id}")
            return False
        
        try:
            # TEST MODE - Skip signature verification
            if PaymentService._is_test_mode():
                logger.info(f"TEST MODE: Auto-verifying payment for token {token_id}")
                
                # Update token with actual payment ID (replacing order ID)
                token.payment_id = payment_id
                token.payment_status = PaymentStatus.COMPLETED
                db.commit()
                
                logger.info(f"✅ TEST MODE: Payment verified for token {token_id}")
                return True
            
            # PRODUCTION MODE - Verify signature
            if not razorpay_signature:
                logger.error("Razorpay signature missing for production verification")
                return False
            
            import razorpay
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            # Verify signature
            params_dict = {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': razorpay_signature
            }
            
            try:
                client.utility.verify_payment_signature(params_dict)
                logger.info(f"✅ Razorpay signature verified for token {token_id}")
            except razorpay.errors.SignatureVerificationError:
                logger.error(f"❌ Razorpay signature verification failed for token {token_id}")
                token.payment_status = PaymentStatus.FAILED
                db.commit()
                return False
            
            # Update token with payment ID
            token.payment_id = payment_id
            token.payment_status = PaymentStatus.COMPLETED
            db.commit()
            
            logger.info(f"✅ Payment verified and completed for token {token_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Payment verification error for token {token_id}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def refund_payment(
        token_id: int,
        reason: str,
        db: Session
    ) -> bool:
        """
        Refund a payment
        
        Args:
            token_id: Payment token ID
            reason: Reason for refund
            db: Database session
            
        Returns:
            bool: True if refund successful
            
        Raises:
            ValueError: If token invalid or cannot be refunded
        """
        
        token = db.query(PaymentToken).filter(PaymentToken.id == token_id).first()
        if not token:
            logger.error(f"Payment token not found: {token_id}")
            raise ValueError("Payment token not found")
        
        if token.payment_status != PaymentStatus.COMPLETED:
            logger.error(f"Cannot refund non-completed payment: {token_id}")
            raise ValueError("Cannot refund non-completed payment")
        
        try:
            # TEST MODE
            if PaymentService._is_test_mode():
                logger.info(f"TEST MODE: Auto-refunding payment token {token_id}")
                refund_id = f"rfnd_TEST_{secrets.token_hex(8)}"
                token.mark_as_refunded(refund_id, reason)
                db.commit()
                return True
            
            # PRODUCTION MODE
            import razorpay
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            logger.info(f"Processing refund for payment: {token.payment_id}")
            refund = client.payment.refund(token.payment_id, {
                "amount": int(token.amount_paid * 100),
                "notes": {"reason": reason}
            })
            
            logger.info(f"Refund processed successfully: {refund['id']}")
            token.mark_as_refunded(refund['id'], reason)
            db.commit()
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Refund failed for token {token_id}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def verify_credentials() -> Dict[str, Any]:
        """
        Verify Razorpay credentials
        
        Returns:
            Dict with verification status
        """
        try:
            if PaymentService._is_test_mode():
                return {
                    "valid": True,
                    "message": "Test mode enabled",
                    "test_mode": True
                }
            
            import razorpay
            
            if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
                return {
                    "valid": False,
                    "message": "Razorpay credentials not configured",
                    "test_mode": False
                }
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            # Test API access
            client.order.all({'count': 1})
            
            return {
                "valid": True,
                "message": "Razorpay credentials are valid",
                "test_mode": settings.RAZORPAY_KEY_ID.startswith('rzp_test_')
            }
        except Exception as e:
            logger.error(f"Credential verification failed: {str(e)}")
            return {
                "valid": False,
                "message": f"Razorpay credentials invalid: {str(e)}",
                "error": str(e)
            }