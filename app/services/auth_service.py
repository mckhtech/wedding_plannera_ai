from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from google.oauth2 import id_token
from google.auth.transport import requests
from app.models.user import User, AuthProvider
from app.schemas.user import UserCreate
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.config import settings

class AuthService:
    @staticmethod
    def register_user(db: Session, user_data: UserCreate) -> User:
        # Check if user exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create new user
        hashed_password = get_password_hash(user_data.password)
        new_user = User(
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            auth_provider=AuthProvider.EMAIL,
            is_verified=False
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User:
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"DEBUG: User not found for email: {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        if user.auth_provider != AuthProvider.EMAIL:
            print(f"DEBUG: User registered with {user.auth_provider}, not email")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Please sign in with {user.auth_provider.value}"
            )
        
        print(f"DEBUG: Verifying password for user: {email}")
        if not verify_password(password, user.hashed_password):
            print("DEBUG: Password verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive"
            )
        
        print("DEBUG: Authentication successful")
        return user
    
    @staticmethod
    def authenticate_google(db: Session, google_token: str) -> User:
        try:
            print(f"DEBUG Google: Attempting to verify token")
            print(f"DEBUG Google: Client ID: {settings.GOOGLE_CLIENT_ID[:20]}...")
            
            # Verify the Google token
            idinfo = id_token.verify_oauth2_token(
                google_token, 
                requests.Request(), 
                settings.GOOGLE_CLIENT_ID
            )
            
            print(f"DEBUG Google: Token verified successfully")
            
            # Get user info from token
            google_id = idinfo['sub']
            email = idinfo['email']
            full_name = idinfo.get('name')
            picture = idinfo.get('picture')
            
            print(f"DEBUG Google: User email: {email}")
            
            # Check if user exists
            user = db.query(User).filter(User.email == email).first()
            
            if user:
                print(f"DEBUG Google: Existing user found")
                # Update Google info if needed
                if user.auth_provider == AuthProvider.EMAIL:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered with password login"
                    )
                
                user.google_id = google_id
                user.profile_picture = picture
                db.commit()
                db.refresh(user)
            else:
                print(f"DEBUG Google: Creating new user")
                # Create new user
                user = User(
                    email=email,
                    full_name=full_name,
                    google_id=google_id,
                    auth_provider=AuthProvider.GOOGLE,
                    profile_picture=picture,
                    is_verified=True  # Google accounts are pre-verified
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            
            return user
            
        except ValueError as e:
            print(f"DEBUG Google: ValueError - {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Google token: {str(e)}"
            )
        except Exception as e:
            print(f"DEBUG Google: Unexpected error - {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Google authentication failed: {str(e)}"
            )
    
    @staticmethod
    def create_token(user: User) -> str:
        access_token = create_access_token(data={"sub": user.email})
        return access_token