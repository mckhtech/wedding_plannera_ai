import boto3
import logging
from pathlib import Path
from typing import Optional, BinaryIO
from botocore.exceptions import ClientError
from app.config import settings
import mimetypes
import uuid

logger = logging.getLogger(__name__)

class S3Service:
    """
    Service for handling AWS S3 operations
    Supports both local and S3 storage based on USE_S3 setting
    """
    
    def __init__(self):
        """Initialize S3 client"""
        if settings.USE_S3:
            try:
                self.s3_client = boto3.client(
                    's3',
                    region_name=settings.AWS_REGION,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
                )
                self.bucket_name = settings.S3_BUCKET_NAME
                logger.info(f"✅ S3 Service initialized - Bucket: {self.bucket_name}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize S3 client: {e}")
                raise
        else:
            self.s3_client = None
            logger.info("ℹ️ S3 disabled - using local storage")
    
    def upload_file(
        self, 
        file_path: str, 
        s3_key: Optional[str] = None,
        folder: str = "uploads"
    ) -> str:
        """
        Upload file to S3 or save locally
        
        Args:
            file_path: Local file path to upload
            s3_key: Custom S3 key (optional, auto-generated if None)
            folder: Folder prefix (uploads/generated/template_previews)
            
        Returns:
            str: S3 URL or local path
        """
        if not settings.USE_S3:
            # Local storage - just return the path
            logger.debug(f"Local storage mode - returning path: {file_path}")
            return file_path
        
        try:
            path = Path(file_path)
            
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Generate S3 key if not provided
            if not s3_key:
                file_extension = path.suffix
                s3_key = f"{folder}/{uuid.uuid4()}{file_extension}"
            
            # Detect content type
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Upload to S3 WITHOUT ACL (bucket policy handles public access)
            extra_args = {
                'ContentType': content_type,
                # REMOVED 'ACL': 'public-read' - causes AccessControlListNotSupported error
            }
            
            self.s3_client.upload_file(
                str(path),
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            
            # Generate public URL
            s3_url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
            
            logger.info(f"✅ Uploaded to S3: {s3_key}")
            return s3_url
            
        except ClientError as e:
            logger.error(f"❌ S3 upload failed: {e}")
            raise Exception(f"Failed to upload to S3: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Upload error: {e}")
            raise
    
    def upload_fileobj(
        self,
        file_obj: BinaryIO,
        filename: str,
        folder: str = "uploads"
    ) -> str:
        """
        Upload file object directly to S3
        
        Args:
            file_obj: File-like object (BytesIO, file handle, etc.)
            filename: Original filename (for extension)
            folder: Folder prefix
            
        Returns:
            str: S3 URL or local path
        """
        if not settings.USE_S3:
            # For local storage, save to disk first
            local_dir = Path(settings.UPLOAD_DIR if folder == "uploads" else settings.GENERATED_DIR)
            local_dir.mkdir(parents=True, exist_ok=True)
            
            file_extension = Path(filename).suffix
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            local_path = local_dir / unique_filename
            
            with open(local_path, 'wb') as f:
                f.write(file_obj.read())
            
            logger.debug(f"Saved locally: {local_path}")
            return str(local_path)
        
        try:
            # Generate S3 key
            file_extension = Path(filename).suffix
            s3_key = f"{folder}/{uuid.uuid4()}{file_extension}"
            
            # Detect content type
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Upload to S3 WITHOUT ACL
            extra_args = {
                'ContentType': content_type,
                # REMOVED 'ACL': 'public-read'
            }
            
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            
            # Generate public URL
            s3_url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
            
            logger.info(f"✅ Uploaded fileobj to S3: {s3_key}")
            return s3_url
            
        except ClientError as e:
            logger.error(f"❌ S3 upload failed: {e}")
            raise Exception(f"Failed to upload to S3: {str(e)}")
    
    def delete_file(self, file_url_or_path: str) -> bool:
        """
        Delete file from S3 or local storage
        
        Args:
            file_url_or_path: S3 URL or local path
            
        Returns:
            bool: True if deleted successfully
        """
        if not settings.USE_S3:
            # Local deletion
            try:
                path = Path(file_url_or_path)
                if path.exists():
                    path.unlink()
                    logger.info(f"🗑️ Deleted local file: {file_url_or_path}")
                    return True
                return False
            except Exception as e:
                logger.error(f"❌ Failed to delete local file: {e}")
                return False
        
        try:
            # Extract S3 key from URL
            s3_key = self._extract_s3_key(file_url_or_path)
            
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            logger.info(f"🗑️ Deleted from S3: {s3_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ S3 deletion failed: {e}")
            return False
    
    def file_exists(self, file_url_or_path: str) -> bool:
        """
        Check if file exists in S3 or locally
        
        Args:
            file_url_or_path: S3 URL or local path
            
        Returns:
            bool: True if file exists
        """
        if not settings.USE_S3:
            return Path(file_url_or_path).exists()
        
        try:
            s3_key = self._extract_s3_key(file_url_or_path)
            
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
            
        except ClientError:
            return False
    
    def _extract_s3_key(self, s3_url: str) -> str:
        """
        Extract S3 key from full S3 URL
        
        Example:
            https://bucket.s3.region.amazonaws.com/uploads/file.jpg
            -> uploads/file.jpg
        """
        if s3_url.startswith('http'):
            # Parse S3 URL
            parts = s3_url.split('.amazonaws.com/')
            if len(parts) > 1:
                return parts[1]
        
        # Assume it's already a key or local path
        return s3_url
    
    def get_file_url(self, s3_key_or_path: str) -> str:
        """
        Get public URL for file
        
        Args:
            s3_key_or_path: S3 key or local path
            
        Returns:
            str: Public URL
        """
        if not settings.USE_S3:
            # Return local URL
            normalized_path = s3_key_or_path.replace('\\', '/')
            if normalized_path.startswith('./'):
                normalized_path = normalized_path[2:]
            
            base_url = settings.BACKEND_URL.rstrip('/')
            if not normalized_path.startswith('/'):
                normalized_path = '/' + normalized_path
            
            return f"{base_url}{normalized_path}"
        
        # Generate S3 URL
        if s3_key_or_path.startswith('http'):
            return s3_key_or_path
        
        return f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key_or_path}"
    
    def test_connection(self) -> bool:
        """
        Test S3 connection
        
        Returns:
            bool: True if connection successful
        """
        if not settings.USE_S3:
            logger.info("ℹ️ S3 disabled - local storage active")
            return True
        
        try:
            # Try to list objects (this will fail if credentials are wrong)
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("✅ S3 connection test successful")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"❌ S3 connection test failed: {error_code}")
            return False
        except Exception as e:
            logger.error(f"❌ S3 connection test failed: {e}")
            return False


# Global instance
s3_service = S3Service()