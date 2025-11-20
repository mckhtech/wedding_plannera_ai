from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.auth import Token, LoginRequest, GoogleAuthRequest
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthService
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.models.payment_token import PaymentToken, TokenStatus, PaymentStatus

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user with email and password"""
    user = AuthService.register_user(db, user_data)
    return user

@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """Login with email and password"""
    user = AuthService.authenticate_user(db, login_data.email, login_data.password)
    access_token = AuthService.create_token(user)
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/google", response_model=Token)
async def google_auth(auth_data: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Authenticate with Google OAuth"""
    user = AuthService.authenticate_google(db, auth_data.token)
    access_token = AuthService.create_token(user)
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@router.get("/verify")
async def verify_token(current_user: User = Depends(get_current_user)):
    """Verify if token is valid"""
    return {"valid": True, "user_id": current_user.id}

# ============================================
# NEW: USER CREDIT & TOKEN INFO
# ============================================

@router.get("/me/credits")
async def get_user_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed credit and token information for current user
    """
    
    # Count unused paid tokens
    unused_tokens = db.query(PaymentToken).filter(
        PaymentToken.user_id == current_user.id,
        PaymentToken.status == TokenStatus.UNUSED,
        PaymentToken.payment_status == PaymentStatus.COMPLETED
    ).all()
    
    # Group by template
    tokens_by_template = {}
    for token in unused_tokens:
        if token.template_id not in tokens_by_template:
            tokens_by_template[token.template_id] = []
        tokens_by_template[token.template_id].append({
            "token_id": token.id,
            "amount_paid": float(token.amount_paid),
            "created_at": token.created_at.isoformat()
        })
    
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "free_credits_remaining": current_user.free_credits_remaining,
        "is_subscribed": current_user.is_subscribed,
        "can_generate_free": current_user.free_credits_remaining > 0,
        "unused_paid_tokens": len(unused_tokens),
        "tokens_by_template": tokens_by_template,
        "message": f"You have {current_user.free_credits_remaining} free generations remaining"
    }