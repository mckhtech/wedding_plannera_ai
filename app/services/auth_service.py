import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from google.oauth2 import id_token
from google.auth.transport import requests
from app.models.user import User, AuthProvider
from app.schemas.user import UserCreate
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.config import settings

logger = logging.getLogger(__name__)

class AuthService:
    @staticmethod
    def register_user(db: Session, user_data: UserCreate) -> User:
        """
        Register a new user with email/password authentication
        
        Args:
            db: Database session
            user_data: User registration data
            
        Returns:
            User: Newly created user object
            
        Raises:
            HTTPException: If email already exists
        """
        try:
            # Check if user exists
            existing_user = db.query(User).filter(User.email == user_data.email).first()
            if existing_user:
                logger.warning(f"Registration attempt with existing email: {user_data.email}")
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
            
            logger.info(f"New user registered: {new_user.email} (ID: {new_user.id})")
            return new_user
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"User registration failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Registration failed. Please try again."
            )
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User:
        """
        Authenticate user with email and password
        
        Args:
            db: Database session
            email: User email
            password: User password
            
        Returns:
            User: Authenticated user object
            
        Raises:
            HTTPException: If authentication fails
        """
        try:
            user = db.query(User).filter(User.email == email).first()
            
            if not user:
                logger.warning(f"Login attempt for non-existent user: {email}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password"
                )
            
            if user.auth_provider != AuthProvider.EMAIL:
                logger.warning(f"Login attempt with wrong provider for {email}: {user.auth_provider}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Please sign in with {user.auth_provider.value}"
                )
            
            if not verify_password(password, user.hashed_password):
                logger.warning(f"Failed login attempt for user: {email}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password"
                )
            
            if not user.is_active:
                logger.warning(f"Login attempt for inactive account: {email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive"
                )
            
            logger.info(f"User authenticated successfully: {email}")
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error for {email}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication failed. Please try again."
            )
    
    @staticmethod
    def authenticate_google(db: Session, google_token: str) -> User:
        """
        Authenticate or register user via Google OAuth
        
        Args:
            db: Database session
            google_token: Google ID token
            
        Returns:
            User: Authenticated/created user object
            
        Raises:
            HTTPException: If Google authentication fails
        """
        try:
            logger.info("Attempting Google authentication")
            
            # Verify the Google token
            idinfo = id_token.verify_oauth2_token(
                google_token, 
                requests.Request(), 
                settings.GOOGLE_CLIENT_ID
            )
            
            # Get user info from token
            google_id = idinfo['sub']
            email = idinfo['email']
            full_name = idinfo.get('name', '')
            picture = idinfo.get('picture')
            
            logger.info(f"Google token verified for email: {email}")
            
            # Check if user exists
            user = db.query(User).filter(User.email == email).first()
            
            if user:
                # Existing user
                if user.auth_provider == AuthProvider.EMAIL:
                    logger.warning(f"Google login attempt for email-registered account: {email}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered with password login. Please use email/password to sign in."
                    )
                
                # Update Google info
                user.google_id = google_id
                user.profile_picture = picture
                db.commit()
                db.refresh(user)
                logger.info(f"Existing Google user logged in: {email}")
            else:
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
                logger.info(f"New Google user created: {email} (ID: {user.id})")
            
            return user
            
        except ValueError as e:
            logger.error(f"Google token validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token"
            )
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Google authentication error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google authentication failed. Please try again."
            )
    
    @staticmethod
    def create_token(user: User) -> str:
        """
        Create JWT access token for user
        
        Args:
            user: User object
            
        Returns:
            str: JWT access token
        """
        try:
            access_token = create_access_token(data={"sub": user.email})
            logger.info(f"Access token created for user: {user.email}")
            return access_token
        except Exception as e:
            logger.error(f"Token creation failed for user {user.email}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create authentication token"
            )