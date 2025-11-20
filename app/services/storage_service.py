import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile, HTTPException, Request
from app.config import settings
from typing import Optional
from contextvars import ContextVar

# Context variable to store current request
_request_context: ContextVar[Optional[Request]] = ContextVar('_request_context', default=None)

class StorageService:
    @staticmethod
    async def save_upload_file(file: UploadFile, folder: str = "uploads") -> str:
        """Save uploaded file and return the file path"""
        # Create directory if not exists
        upload_dir = Path(settings.UPLOAD_DIR if folder == "uploads" else settings.GENERATED_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename
        
        # Save file
        try:
            async with aiofiles.open(file_path, 'wb') as out_file:
                content = await file.read()
                await out_file.write(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
        return str(file_path)
    
    @staticmethod
    def get_file_url(file_path: Optional[str], request: Optional[Request] = None) -> Optional[str]:
        """
        Convert file path to URL
        Handles both forward slashes and backslashes (Windows paths)
        Automatically detects if request is from ngrok or localhost
        """
        if not file_path:
            return None
        
        # Normalize path separators - convert backslashes to forward slashes
        normalized_path = file_path.replace('\\', '/')
        
        # Remove leading "./" if present
        if normalized_path.startswith('./'):
            normalized_path = normalized_path[2:]
        
        # Try to get base URL from request context (for ngrok support)
        base_url = settings.BACKEND_URL
        
        if request:
            # Extract base URL from request
            scheme = request.url.scheme  # http or https
            host = request.headers.get("host")  # includes ngrok domain
            if host:
                base_url = f"{scheme}://{host}"
        
        # Ensure base_url doesn't end with slash
        base_url = base_url.rstrip('/')
        
        # Ensure path starts with slash
        if not normalized_path.startswith('/'):
            normalized_path = '/' + normalized_path
        
        return f"{base_url}{normalized_path}"
    
    @staticmethod
    def delete_file(file_path: str) -> bool:
        """Delete a file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def validate_image_file(file: UploadFile) -> bool:
        """Validate if uploaded file is an image"""
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # Check file size
        if file.size and file.size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE / 1024 / 1024}MB"
            )
        
        return True
    
    @staticmethod
    def file_exists(file_path: str) -> bool:
        """Check if file exists"""
        return Path(file_path).exists()
    
    @staticmethod
    def get_file_size(file_path: str) -> Optional[int]:
        """Get file size in bytes"""
        try:
            return Path(file_path).stat().st_size
        except Exception:
            return None