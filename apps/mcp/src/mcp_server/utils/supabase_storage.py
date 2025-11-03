"""Supabase Storage utilities for agent output management."""

import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict

from ..config import settings
from .exceptions import ConfigurationError, ToolExecutionError
from .logging import get_logger

logger = get_logger(__name__)


def is_supabase_storage_available() -> bool:
    """Check if Supabase Storage is available and configured."""
    try:
        # Check if supabase library is installed
        import supabase

        # Check for required configuration
        if not settings.supabase_url or not settings.supabase_service_key:
            logger.warning("Supabase URL or service role key not configured")
            return False

        return True
    except ImportError:
        logger.info("Supabase library not installed - Supabase storage disabled")
        return False


def fix_storage_url_for_development(url: str) -> str:
    """
    Replace kong:8000 with localhost:8000 in development environments.

    This is needed because:
    - Supabase in Docker uses SUPABASE_URL=http://kong:8000 for internal communication
    - Browser cannot resolve 'kong' hostname in development
    - localhost:8000 works for both Docker and local development
    """
    # Check if we're in development mode (default to development if not set)
    is_development = os.getenv("ENVIRONMENT", "development") == "development"

    if is_development and "kong:8000" in url:
        return url.replace("kong:8000", "localhost:8000")

    return url


class SupabaseStorageClient:
    """Singleton Supabase Storage client for agent output management."""

    _instance = None
    _client = None
    _bucket_name = "agent-outputs"

    @classmethod
    def get_client(cls):
        """Get or create Supabase client instance."""
        if not is_supabase_storage_available():
            raise ConfigurationError("Supabase Storage is not available or configured")

        if cls._client is None:
            try:
                # Lazy import supabase
                from supabase import create_client

                cls._client = create_client(
                    settings.supabase_url,
                    settings.supabase_service_key
                )
                logger.info("Supabase Storage client initialized")

            except Exception as e:
                raise ConfigurationError(f"Failed to initialize Supabase Storage client: {str(e)}")

        return cls._client

    @classmethod
    def get_bucket_name(cls) -> str:
        """Get the bucket name for agent outputs."""
        return cls._bucket_name


@dataclass
class OutputMetadata:
    """Metadata for stored agent outputs."""

    filename: str
    user_id: str
    assistant_id: str
    thread_id: str
    tool_name: str
    content_type: str
    size_bytes: int
    format: str = "png"
    created_at: str = None
    additional_metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Set created_at after initialization if not provided."""
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
        if self.additional_metadata is None:
            self.additional_metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        base_dict = asdict(self)
        # Merge additional_metadata into the base dict
        additional = base_dict.pop('additional_metadata', {})
        base_dict.update(additional)
        return base_dict


def generate_output_filename(
    user_id: str,
    assistant_id: str,
    thread_id: str,
    tool_name: str,
    format: str = "png"
) -> str:
    """
    Generate unique filename for agent output.

    Path structure: {user_id}/{assistant_id}/{thread_id}/{tool_name}_{timestamp}_{unique_id}.{format}

    Args:
        user_id: User ID (top-level for RLS)
        assistant_id: Assistant/agent ID
        thread_id: Thread/conversation ID
        tool_name: Name of the tool generating the output
        format: File extension (default: png)

    Returns:
        Full storage path including folder structure
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    filename = f"{tool_name}_{timestamp}_{unique_id}.{format}"

    # Clean IDs to ensure they're filesystem-safe
    clean_user_id = user_id.replace(" ", "_")
    clean_assistant_id = assistant_id.replace(" ", "_")
    clean_thread_id = thread_id.replace(" ", "_")

    return f"{clean_user_id}/{clean_assistant_id}/{clean_thread_id}/{filename}"


def upload_output_to_supabase(
    output_data: bytes,
    metadata: OutputMetadata,
    content_type: str = "image/png"
) -> Tuple[str, str]:
    """
    Upload agent output to Supabase Storage.

    Args:
        output_data: Binary output data
        metadata: Output metadata
        content_type: MIME type (e.g., 'image/png', 'image/svg+xml')

    Returns:
        Tuple of (filename, signed_url)

    Raises:
        ConfigurationError: If storage is not configured
        ToolExecutionError: If upload fails
    """
    try:
        client = SupabaseStorageClient.get_client()
        bucket_name = SupabaseStorageClient.get_bucket_name()

        # Upload to Supabase Storage
        response = client.storage.from_(bucket_name).upload(
            path=metadata.filename,
            file=output_data,
            file_options={
                "content-type": content_type,
                "cache-control": "3600",
                "upsert": "false"  # Don't overwrite existing files
            }
        )

        logger.info(
            "Output uploaded to Supabase Storage",
            filename=metadata.filename,
            size_bytes=len(output_data),
            user_id=metadata.user_id,
            assistant_id=metadata.assistant_id,
            thread_id=metadata.thread_id,
            tool_name=metadata.tool_name
        )

        # Generate signed URL for download (30 minute expiry)
        signed_url = generate_signed_url(metadata.filename, expiry_seconds=1800)

        return metadata.filename, signed_url

    except Exception as e:
        logger.error(
            "Failed to upload output to Supabase Storage",
            error=str(e),
            filename=metadata.filename,
            user_id=metadata.user_id
        )
        raise ToolExecutionError("supabase_storage", f"Failed to upload output: {str(e)}")


def generate_signed_url(filename: str, expiry_seconds: int = 1800) -> str:
    """
    Generate signed URL for temporary access to an output file.

    Args:
        filename: Supabase Storage path (including folder structure)
        expiry_seconds: URL expiry time in seconds (default: 30 minutes)

    Returns:
        Signed URL for file access

    Raises:
        ConfigurationError: If storage is not configured
        ToolExecutionError: If URL generation fails
    """
    try:
        client = SupabaseStorageClient.get_client()
        bucket_name = SupabaseStorageClient.get_bucket_name()

        # Generate signed URL
        signed_url_response = client.storage.from_(bucket_name).create_signed_url(
            path=filename,
            expires_in=expiry_seconds
        )

        if not signed_url_response or 'signedURL' not in signed_url_response:
            raise ToolExecutionError(
                "supabase_storage",
                f"Failed to generate signed URL: Invalid response"
            )

        signed_url = signed_url_response['signedURL']

        # Fix URL for development environment
        signed_url = fix_storage_url_for_development(signed_url)

        logger.debug(
            "Generated signed URL",
            filename=filename,
            expiry_seconds=expiry_seconds
        )

        return signed_url

    except Exception as e:
        logger.error(
            "Failed to generate signed URL",
            error=str(e),
            filename=filename
        )
        raise ToolExecutionError("supabase_storage", f"Failed to generate signed URL: {str(e)}")


def get_public_url(filename: str) -> str:
    """
    Get public URL for an output file (if bucket is public).

    Note: agent-outputs bucket is private, so this will not work without proper authentication.
    Use generate_signed_url() instead for temporary access.

    Args:
        filename: Supabase Storage path

    Returns:
        Public URL (may not be accessible if bucket is private)
    """
    try:
        client = SupabaseStorageClient.get_client()
        bucket_name = SupabaseStorageClient.get_bucket_name()

        public_url = client.storage.from_(bucket_name).get_public_url(filename)

        # Fix URL for development environment
        public_url = fix_storage_url_for_development(public_url)

        return public_url

    except Exception as e:
        logger.error(
            "Failed to get public URL",
            error=str(e),
            filename=filename
        )
        raise ToolExecutionError("supabase_storage", f"Failed to get public URL: {str(e)}")
