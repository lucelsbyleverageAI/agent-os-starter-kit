"""Google Cloud Storage utilities for image management."""

import base64
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from ..config import settings
from .exceptions import ConfigurationError, ToolExecutionError
from .logging import get_logger

logger = get_logger(__name__)


def is_gcp_available() -> bool:
    """Check if GCP Storage is available and configured."""
    try:
        # Check if google-cloud-storage is installed
        import google.cloud.storage
        import google.oauth2.service_account
        
        # Check for project ID
        if not settings.gcp_project_id:
            return False
        
        # Check for any valid credential source
        has_creds = any([
            settings.gcp_service_account_key,
            settings.gcp_credentials_json,
            settings.gcp_credentials_path and os.path.exists(settings.gcp_credentials_path),
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # Default credential discovery
        ])
        
        return has_creds
    except ImportError:
        logger.info("Google Cloud Storage libraries not installed - GCP storage disabled")
        return False


def decode_base64_to_bytes(base64_string: str) -> bytes:
    """Decode base64 string to bytes."""
    try:
        return base64.b64decode(base64_string)
    except Exception as e:
        raise ToolExecutionError("gcp_storage", f"Failed to decode base64 image: {str(e)}")


class GCPStorageClient:
    """Singleton GCP Storage client for image management."""
    
    _instance = None
    _bucket = None
    
    @classmethod
    def get_client(cls):
        """Get or create GCP Storage client instance."""
        if not is_gcp_available():
            raise ConfigurationError("GCP Storage is not available or configured")
            
        if cls._instance is None:
            try:
                # Lazy import GCP libraries
                from google.cloud import storage
                from google.oauth2 import service_account
                
                # Try base64 encoded service account key first (for production)
                if settings.gcp_service_account_key:
                    try:
                        # Decode base64 and parse JSON
                        service_account_key_json = base64.b64decode(settings.gcp_service_account_key).decode('utf-8')
                        credentials_info = json.loads(service_account_key_json)
                        credentials = service_account.Credentials.from_service_account_info(
                            credentials_info
                        )
                        cls._instance = storage.Client(
                            project=settings.gcp_project_id,
                            credentials=credentials
                        )
                        logger.info("GCP Storage client initialized from base64 service account key")
                    except Exception as e:
                        logger.error(f"Failed to parse base64 service account key: {str(e)}")
                        raise ConfigurationError(f"Invalid base64 service account key: {str(e)}")
                
                # Try credentials JSON string (for direct JSON env vars)
                elif settings.gcp_credentials_json:
                    credentials_info = json.loads(settings.gcp_credentials_json)
                    credentials = service_account.Credentials.from_service_account_info(
                        credentials_info
                    )
                    cls._instance = storage.Client(
                        project=settings.gcp_project_id,
                        credentials=credentials
                    )
                    logger.info("GCP Storage client initialized from JSON credentials")
                
                # Try credentials file path (for local development)
                elif settings.gcp_credentials_path and os.path.exists(settings.gcp_credentials_path):
                    credentials = service_account.Credentials.from_service_account_file(
                        settings.gcp_credentials_path
                    )
                    cls._instance = storage.Client(
                        project=settings.gcp_project_id,
                        credentials=credentials
                    )
                    logger.info("GCP Storage client initialized from credentials file")
                
                # Try default credentials (for GCP environments)
                else:
                    cls._instance = storage.Client(project=settings.gcp_project_id)
                    logger.info("GCP Storage client initialized with default credentials")
                    
            except Exception as e:
                raise ConfigurationError(f"Failed to initialize GCP Storage client: {str(e)}")
        
        return cls._instance
    
    @classmethod
    def get_bucket(cls):
        """Get or create GCP Storage bucket instance."""
        if cls._bucket is None:
            # Lazy import for exceptions
            from google.cloud.exceptions import NotFound
            
            client = cls.get_client()
            try:
                cls._bucket = client.bucket(settings.gcp_storage_bucket)
                # Test bucket access
                cls._bucket.exists()
                logger.info(f"Connected to GCP Storage bucket: {settings.gcp_storage_bucket}")
            except NotFound:
                raise ConfigurationError(f"GCP Storage bucket '{settings.gcp_storage_bucket}' not found")
            except Exception as e:
                raise ConfigurationError(f"Failed to access GCP Storage bucket: {str(e)}")
        
        return cls._bucket


class ImageMetadata:
    """Metadata for stored images."""
    
    def __init__(
        self,
        filename: str,
        user_id: str,
        tool_name: str,
        original_prompt: str,
        size: str = "auto",
        quality: str = "auto",
        format: str = "png",
        additional_metadata: Optional[Dict[str, Any]] = None
    ):
        self.filename = filename
        self.user_id = user_id
        self.tool_name = tool_name
        self.original_prompt = original_prompt
        self.size = size
        self.quality = quality
        self.format = format
        self.created_at = datetime.utcnow().isoformat()
        self.additional_metadata = additional_metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "filename": self.filename,
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "original_prompt": self.original_prompt,
            "size": self.size,
            "quality": self.quality,
            "format": self.format,
            "created_at": self.created_at,
            **self.additional_metadata
        }


def generate_image_filename(user_id: str, tool_name: str, format: str = "png") -> str:
    """Generate unique filename for image."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"images/{user_id}/{tool_name}/{timestamp}_{unique_id}.{format}"


def upload_image_to_gcp(
    image_data: bytes,
    metadata: ImageMetadata,
    content_type: str = "image/png"
) -> Tuple[str, str]:
    """
    Upload image to GCP Storage.
    
    Returns:
        Tuple of (filename, download_url)
    """
    if not settings.image_storage_enabled:
        raise ConfigurationError("Image storage is disabled")
    
    try:
        bucket = GCPStorageClient.get_bucket()
        
        # Create blob with filename
        blob = bucket.blob(metadata.filename)
        
        # Set metadata
        blob.metadata = metadata.to_dict()
        blob.content_type = content_type
        
        # Upload image data
        blob.upload_from_string(image_data, content_type=content_type)
        
        logger.info(
            "Image uploaded to GCP Storage",
            filename=metadata.filename,
            size_bytes=len(image_data),
            user_id=metadata.user_id,
            tool_name=metadata.tool_name
        )
        
        # Generate signed URL for download
        download_url = generate_signed_url(metadata.filename)
        
        return metadata.filename, download_url
        
    except Exception as e:
        logger.error(
            "Failed to upload image to GCP Storage",
            error=str(e),
            filename=metadata.filename,
            user_id=metadata.user_id
        )
        raise ToolExecutionError("gcp_storage", f"Failed to upload image: {str(e)}")


def generate_signed_url(filename: str, expiry_hours: Optional[int] = None) -> str:
    """
    Generate signed URL for image access.
    
    Args:
        filename: GCP Storage blob name
        expiry_hours: URL expiry time in hours (defaults to config setting)
                     Set to 0 or None with public_access=True for public URLs
    
    Returns:
        Signed URL or public URL for image access
    """
    try:
        bucket = GCPStorageClient.get_bucket()
        blob = bucket.blob(filename)
        
        # Check if public access is enabled
        if settings.image_public_access:
            # Return public URL (no expiry, no signature)
            base_url = settings.image_base_url or f"https://storage.googleapis.com/{settings.gcp_storage_bucket}"
            public_url = f"{base_url}/{filename}"
            
            logger.info(
                "Generated public URL",
                filename=filename,
                url_type="public"
            )
            return public_url
        
        # Use expiry hours setting
        expiry_hours = expiry_hours or settings.image_url_expiry_hours
        
        # Handle special case for very long expiry (treat as max allowed)
        if expiry_hours == 0 or expiry_hours > 8760:  # 8760 = 1 year
            # Set to maximum allowed (7 days for signed URLs)
            expiry_hours = 168  # 7 days
            logger.warning(
                "Expiry time capped at maximum allowed",
                requested_hours=expiry_hours,
                actual_hours=168,
                filename=filename
            )
        
        expiry_time = datetime.utcnow() + timedelta(hours=expiry_hours)
        
        # Generate signed URL
        signed_url = blob.generate_signed_url(
            expiration=expiry_time,
            method="GET"
        )
        
        logger.info(
            "Generated signed URL",
            filename=filename,
            expiry_hours=expiry_hours,
            url_type="signed"
        )
        
        return signed_url
        
    except Exception as e:
        logger.error(
            "Failed to generate URL",
            error=str(e),
            filename=filename
        )
        raise ToolExecutionError("gcp_storage", f"Failed to generate URL: {str(e)}")


def get_image_metadata(filename: str) -> Optional[Dict[str, Any]]:
    """
    Get image metadata from GCP Storage.
    
    Args:
        filename: GCP Storage blob name
    
    Returns:
        Image metadata dictionary or None if not found
    """
    try:
        bucket = GCPStorageClient.get_bucket()
        blob = bucket.blob(filename)
        
        if not blob.exists():
            return None
        
        # Reload to get metadata
        blob.reload()
        
        return blob.metadata
        
    except Exception as e:
        logger.error(
            "Failed to get image metadata",
            error=str(e),
            filename=filename
        )
        return None


def delete_image(filename: str) -> bool:
    """
    Delete image from GCP Storage.
    
    Args:
        filename: GCP Storage blob name
    
    Returns:
        True if successfully deleted, False otherwise
    """
    try:
        bucket = GCPStorageClient.get_bucket()
        blob = bucket.blob(filename)
        
        if blob.exists():
            blob.delete()
            logger.info("Image deleted from GCP Storage", filename=filename)
            return True
        else:
            logger.warning("Image not found for deletion", filename=filename)
            return False
            
    except Exception as e:
        logger.error(
            "Failed to delete image",
            error=str(e),
            filename=filename
        )
        return False


def list_user_images(
    user_id: str, 
    tool_name: Optional[str] = None,
    limit: int = 100
) -> list[Dict[str, Any]]:
    """
    List images for a user.
    
    Args:
        user_id: User ID to filter by
        tool_name: Optional tool name to filter by
        limit: Maximum number of results
    
    Returns:
        List of image metadata dictionaries
    """
    try:
        bucket = GCPStorageClient.get_bucket()
        
        # Build prefix for user's images
        prefix = f"images/{user_id}/"
        if tool_name:
            prefix += f"{tool_name}/"
        
        # List blobs with prefix
        blobs = bucket.list_blobs(prefix=prefix, max_results=limit)
        
        images = []
        for blob in blobs:
            blob.reload()  # Get metadata
            
            image_info = {
                "filename": blob.name,
                "created": blob.time_created.isoformat() if blob.time_created else None,
                "size_bytes": blob.size,
                "content_type": blob.content_type,
                "metadata": blob.metadata or {},
                "download_url": generate_signed_url(blob.name)
            }
            images.append(image_info)
        
        return images
        
    except Exception as e:
        logger.error(
            "Failed to list user images",
            error=str(e),
            user_id=user_id,
            tool_name=tool_name
        )
        return []


def configure_bucket_public_access(enable: bool = True) -> bool:
    """
    Configure bucket for public read access.
    
    Args:
        enable: True to enable public access, False to disable
    
    Returns:
        True if successful, False otherwise
        
    Note:
        This function requires the service account to have 
        "Storage Admin" role, not just "Storage Object Admin"
    """
    try:
        bucket = GCPStorageClient.get_bucket()
        
        if enable:
            # Make bucket publicly readable
            policy = bucket.get_iam_policy(requested_policy_version=3)
            policy.bindings.append({
                "role": "roles/storage.objectViewer",
                "members": ["allUsers"]
            })
            bucket.set_iam_policy(policy)
            
            logger.info(
                "Bucket configured for public access",
                bucket_name=bucket.name
            )
        else:
            # Remove public access
            policy = bucket.get_iam_policy(requested_policy_version=3)
            policy.bindings = [
                binding for binding in policy.bindings
                if not (binding["role"] == "roles/storage.objectViewer" 
                       and "allUsers" in binding["members"])
            ]
            bucket.set_iam_policy(policy)
            
            logger.info(
                "Public access removed from bucket",
                bucket_name=bucket.name
            )
        
        return True
        
    except Exception as e:
        logger.error(
            "Failed to configure bucket public access",
            error=str(e),
            enable=enable
        )
        return False


def get_public_url(filename: str) -> str:
    """
    Get public URL for a file (bucket must be configured for public access).
    
    Args:
        filename: GCP Storage blob name
    
    Returns:
        Public URL (no expiry, no signature required)
    """
    base_url = settings.image_base_url or f"https://storage.googleapis.com/{settings.gcp_storage_bucket}"
    return f"{base_url}/{filename}"


def download_image_from_gcp(filename: str) -> bytes:
    """
    Download image bytes from GCP Storage.
    
    Args:
        filename: GCP Storage blob name
    
    Returns:
        Image bytes
    
    Raises:
        ToolExecutionError: If download fails
    """
    try:
        bucket = GCPStorageClient.get_bucket()
        blob = bucket.blob(filename)
        
        if not blob.exists():
            raise ToolExecutionError("gcp_storage", f"Image not found: {filename}")
        
        # Download image bytes
        image_bytes = blob.download_as_bytes()
        
        logger.info(
            "Downloaded image from GCP Storage",
            filename=filename,
            size_bytes=len(image_bytes)
        )
        
        return image_bytes
        
    except Exception as e:
        logger.error(
            "Failed to download image from GCP Storage",
            error=str(e),
            filename=filename
        )
        raise ToolExecutionError("gcp_storage", f"Failed to download image from GCP: {str(e)}") 