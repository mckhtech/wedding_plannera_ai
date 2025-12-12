import os
import uuid
import aiofiles
import logging
from pathlib import Path
from fastapi import UploadFile, HTTPException, Request
from app.config import settings
from app.services.s3_service import s3_service
from typing import Optional
import tempfile

logger = logging.getLogger(__name__)

class StorageService:
    """
    Unified storage service supporting both local and S3 storage
    Automatically switches based on USE_S3 setting
    """
    
    # Allowed file extensions and their MIME types
    ALLOWED_IMAGE_TYPES = {
        '.jpg': ['image/jpeg'],
        '.jpeg': ['image/jpeg'],
        '.png': ['image/png'],
        '.webp': ['image/webp']
    }
    
    @staticmethod
    async def save_upload_file(file: UploadFile, folder: str = "uploads") -> str:
        """
        Save uploaded file to S3 or local storage
        
        Args:
            file: Uploaded file object
            folder: Target folder ("uploads", "generated", or "template_previews")
            
        Returns:
            str: S3 URL or local file path
            
        Raises:
            HTTPException: If file save fails
        """
        try:
            # Validate file first
            StorageService.validate_image_file(file)
            
            # Read file content
            content = await file.read()
            
            if settings.USE_S3:
                # Upload to S3
                from io import BytesIO
                file_obj = BytesIO(content)
                
                s3_url = s3_service.upload_fileobj(
                    file_obj=file_obj,
                    filename=file.filename,
                    folder=folder
                )
                
                logger.info(f"✅ File uploaded to S3: {s3_url}")
                return s3_url
                
            else:
                # Save locally
                upload_dir = Path(settings.UPLOAD_DIR if folder == "uploads" else settings.GENERATED_DIR)
                if folder == "template_previews":
                    upload_dir = Path(settings.TEMPLATE_PREVIEW_DIR)
                    
                upload_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate unique filename
                file_extension = os.path.splitext(file.filename)[1].lower()
                unique_filename = f"{uuid.uuid4()}{file_extension}"
                file_path = upload_dir / unique_filename
                
                # Save file
                async with aiofiles.open(file_path, 'wb') as out_file:
                    await out_file.write(content)
                
                logger.info(f"✅ File saved locally: {file_path} ({len(content)} bytes)")
                return str(file_path)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to save file: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to save file: {str(e)}"
            )
    
    @staticmethod
    def save_generated_image(image_path: str, folder: str = "generated") -> str:
        """
        Upload already-generated local image to S3
        
        Args:
            image_path: Local path to generated image
            folder: S3 folder prefix
            
        Returns:
            str: S3 URL or local path
        """
        if not settings.USE_S3:
            return image_path
        
        try:
            s3_url = s3_service.upload_file(
                file_path=image_path,
                folder=folder
            )
            
            # Optionally delete local file after upload
            try:
                Path(image_path).unlink()
                logger.debug(f"🗑️ Deleted local file after S3 upload: {image_path}")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete local file: {e}")
            
            return s3_url
            
        except Exception as e:
            logger.error(f"❌ Failed to upload generated image to S3: {e}")
            # Fallback to local path if S3 fails
            return image_path
    
    @staticmethod
    def get_file_url(file_path: Optional[str], request: Optional[Request] = None) -> Optional[str]:
        """
        Convert file path/URL to accessible URL
        
        Args:
            file_path: S3 URL or local file path
            request: FastAPI request object (optional, for dynamic base URL)
            
        Returns:
            Optional[str]: Full URL to file or None if path is None
        """
        if not file_path:
            return None
        
        try:
            # If already a full URL (S3), return as-is
            if file_path.startswith('http'):
                return file_path
            
            if settings.USE_S3:
                # Generate S3 URL
                return s3_service.get_file_url(file_path)
            
            # Local storage - generate local URL
            normalized_path = file_path.replace('\\', '/')
            
            # Remove leading "./"
            if normalized_path.startswith('./'):
                normalized_path = normalized_path[2:]
            
            # Get base URL
            base_url = settings.BACKEND_URL
            
            # Use request to get dynamic base URL (supports ngrok)
            if request:
                scheme = request.url.scheme
                host = request.headers.get("host")
                if host:
                    base_url = f"{scheme}://{host}"
            
            # Ensure proper URL format
            base_url = base_url.rstrip('/')
            if not normalized_path.startswith('/'):
                normalized_path = '/' + normalized_path
            
            final_url = f"{base_url}{normalized_path}"
            logger.debug(f"Generated file URL: {final_url}")
            return final_url
            
        except Exception as e:
            logger.error(f"Failed to generate file URL: {str(e)}")
            return None
    
    @staticmethod
    def delete_file(file_path: str) -> bool:
        """
        Delete a file from S3 or local storage
        
        Args:
            file_path: S3 URL or local path
            
        Returns:
            bool: True if deleted, False otherwise
        """
        return s3_service.delete_file(file_path)
    
    @staticmethod
    def validate_image_file(file: UploadFile) -> bool:
        """
        Validate uploaded file is a valid image
        
        Args:
            file: Uploaded file object
            
        Returns:
            bool: True if valid
            
        Raises:
            HTTPException: If validation fails
        """
        # Check file extension
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if file_extension not in StorageService.ALLOWED_IMAGE_TYPES:
            logger.warning(f"Invalid file type attempted: {file_extension}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed types: {', '.join(StorageService.ALLOWED_IMAGE_TYPES.keys())}"
            )
        
        # Check MIME type if available
        if file.content_type:
            allowed_mimes = StorageService.ALLOWED_IMAGE_TYPES[file_extension]
            if file.content_type not in allowed_mimes:
                logger.warning(f"MIME type mismatch: {file.content_type} for {file_extension}")
                raise HTTPException(
                    status_code=400,
                    detail="File type does not match file extension"
                )
        
        # Check file size
        if hasattr(file, 'size') and file.size:
            if file.size > settings.MAX_FILE_SIZE:
                max_size_mb = settings.MAX_FILE_SIZE / 1024 / 1024
                logger.warning(f"File too large: {file.size} bytes (max: {settings.MAX_FILE_SIZE})")
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large. Maximum size: {max_size_mb:.1f}MB"
                )
        
        logger.debug(f"File validation passed: {file.filename}")
        return True
    
    @staticmethod
    def file_exists(file_path: str) -> bool:
        """
        Check if file exists in S3 or locally
        
        Args:
            file_path: S3 URL or local path
            
        Returns:
            bool: True if exists
        """
        return s3_service.file_exists(file_path)
    
    @staticmethod
    def get_file_size(file_path: str) -> Optional[int]:
        """
        Get file size in bytes (local only for now)
        
        Args:
            file_path: Path to file
            
        Returns:
            Optional[int]: File size in bytes or None if error
        """
        if settings.USE_S3:
            logger.warning("get_file_size not implemented for S3 yet")
            return None
            
        try:
            size = Path(file_path).stat().st_size
            logger.debug(f"File size for {file_path}: {size} bytes")
            return size
        except Exception as e:
            logger.error(f"Error getting file size: {str(e)}")
            return None
    
    @staticmethod
    def cleanup_old_files(directory: str, max_age_days: int = 7) -> int:
        """
        Clean up old files from local directory
        (S3 cleanup handled by lifecycle policies)
        
        Args:
            directory: Directory to clean
            max_age_days: Delete files older than this many days
            
        Returns:
            int: Number of files deleted
        """
        if settings.USE_S3:
            logger.info("S3 cleanup handled by lifecycle policies")
            return 0
            
        try:
            import time
            
            dir_path = Path(directory)
            if not dir_path.exists():
                return 0
            
            deleted_count = 0
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            for file_path in dir_path.glob('*'):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        try:
                            file_path.unlink()
                            deleted_count += 1
                            logger.info(f"Deleted old file: {file_path}")
                        except Exception as e:
                            logger.error(f"Failed to delete {file_path}: {str(e)}")
            
            logger.info(f"Cleanup completed: {deleted_count} files deleted from {directory}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Cleanup failed for {directory}: {str(e)}")
            return 0