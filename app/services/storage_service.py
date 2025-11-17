import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile, HTTPException
from app.config import settings

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
    def get_file_url(file_path: str) -> str:
        """Convert file path to URL"""
        # For local storage, return relative path
        # You can modify this for cloud storage later
        return f"{settings.BACKEND_URL}/{file_path}"
    
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