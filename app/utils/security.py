from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
import hashlib
from app.config import settings

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hashed password"""
    password_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    print(f"DEBUG Login - Pre-hashed password: {password_hash[:20]}...")
    print(f"DEBUG Login - Stored hash: {hashed_password[:20]}...")
    
    try:
        result = bcrypt.checkpw(password_hash.encode('utf-8'), hashed_password.encode('utf-8'))
        print(f"DEBUG Login - Password match: {result}")
        return result
    except Exception as e:
        print(f"DEBUG Login - Error: {e}")
        return False

def get_password_hash(password: str) -> str:
    """Hash a password using SHA256 + bcrypt"""
    # Pre-hash with SHA256 to handle passwords of any length
    password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    print(f"DEBUG: Pre-hashed password length: {len(password_hash)}")  # Remove after testing
    
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_hash.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    """Decode a JWT access token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None