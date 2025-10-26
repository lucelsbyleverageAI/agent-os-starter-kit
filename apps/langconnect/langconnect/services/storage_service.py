"""Supabase Storage service for managing image uploads."""

import logging
from typing import Optional, BinaryIO
from datetime import datetime
from supabase import create_client

from langconnect import config

logger = logging.getLogger(__name__)

# Configuration - hard-coded for consistency across deployments
COLLECTIONS_BUCKET = "collections"
CHAT_UPLOADS_BUCKET = "chat-uploads"
SIGNED_URL_EXPIRY_SECONDS = 1800  # 30 minutes


class StorageService:
    """Service for managing file storage in Supabase Storage."""

    def __init__(self):
        """Initialize the storage service."""
        self.client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        self.collections_bucket = COLLECTIONS_BUCKET
        self.chat_uploads_bucket = CHAT_UPLOADS_BUCKET
        self.signed_url_expiry = SIGNED_URL_EXPIRY_SECONDS

    def _generate_storage_path(
        self,
        collection_uuid: str,
        filename: str
    ) -> str:
        """Generate a storage path for an uploaded file.

        Format: {collection_uuid}/{timestamp}_{filename}

        Args:
            collection_uuid: UUID of the collection
            filename: Original filename

        Returns:
            Storage path string
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = filename.replace(" ", "_")
        return f"{collection_uuid}/{timestamp}_{safe_filename}"

    async def upload_image(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        collection_uuid: str
    ) -> dict:
        """Upload an image file to Supabase Storage.

        Args:
            file_data: Binary file content
            filename: Original filename
            content_type: MIME type (e.g., 'image/jpeg')
            collection_uuid: UUID of the collection

        Returns:
            dict with:
                - storage_path: storage://bucket/path format
                - public_url: Public URL if bucket is public
                - file_path: Path within bucket

        Raises:
            Exception: If upload fails
        """
        try:
            # Generate storage path
            file_path = self._generate_storage_path(collection_uuid, filename)

            # Upload to Supabase Storage
            response = self.client.storage.from_(self.collections_bucket).upload(
                path=file_path,
                file=file_data,
                file_options={
                    "content-type": content_type,
                    "cache-control": "3600",
                    "upsert": "false"  # Don't overwrite existing files
                }
            )

            logger.info(f"Uploaded image to storage: {file_path}")

            # Generate storage URI
            storage_uri = f"storage://{self.collections_bucket}/{file_path}"

            # Get public URL (if bucket is public)
            public_url = self.client.storage.from_(self.collections_bucket).get_public_url(file_path)

            return {
                "storage_path": storage_uri,
                "public_url": public_url,
                "file_path": file_path,
                "bucket": self.collections_bucket
            }

        except Exception as e:
            logger.error(f"Failed to upload image to storage: {e}")
            raise

    def _generate_chat_storage_path(
        self,
        user_id: str,
        filename: str
    ) -> str:
        """Generate a storage path for a chat upload.

        Format: {user_id}/{timestamp}_{filename}

        Args:
            user_id: UUID of the user
            filename: Original filename

        Returns:
            Storage path string
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        safe_filename = filename.replace(" ", "_")
        return f"{user_id}/{timestamp}_{safe_filename}"

    async def upload_chat_image(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        user_id: str,
    ) -> dict:
        """Upload a chat image file to Supabase Storage.

        Args:
            file_data: Binary file content
            filename: Original filename
            content_type: MIME type (e.g., 'image/jpeg')
            user_id: UUID of the user

        Returns:
            dict with:
                - storage_path: Just the path within bucket (for message content)
                - file_path: Same as storage_path
                - bucket: Bucket name

        Raises:
            Exception: If upload fails
        """
        try:
            # Generate storage path
            file_path = self._generate_chat_storage_path(user_id, filename)

            # Upload to Supabase Storage
            response = self.client.storage.from_(self.chat_uploads_bucket).upload(
                path=file_path,
                file=file_data,
                file_options={
                    "content-type": content_type,
                    "cache-control": "3600",
                    "upsert": "false"  # Don't overwrite existing files
                }
            )

            logger.info(f"Uploaded chat image to storage: {file_path}")

            # Return just the storage path (will be converted to signed URL at runtime)
            return {
                "storage_path": file_path,  # Just the path, not storage:// URI
                "file_path": file_path,
                "bucket": self.chat_uploads_bucket
            }

        except Exception as e:
            logger.error(f"Failed to upload chat image to storage: {e}")
            raise

    async def get_signed_url(
        self,
        file_path: str,
        expiry_seconds: Optional[int] = None,
        bucket: Optional[str] = None
    ) -> str:
        """Generate a signed URL for temporary access to a file.

        Args:
            file_path: Path within bucket (not storage:// URI)
            expiry_seconds: Expiry time in seconds (default: 30 minutes)
            bucket: Bucket name (default: collections bucket)

        Returns:
            Signed URL string

        Raises:
            Exception: If URL generation fails
        """
        try:
            expiry = expiry_seconds or self.signed_url_expiry
            bucket_name = bucket or self.collections_bucket

            response = self.client.storage.from_(bucket_name).create_signed_url(
                path=file_path,
                expires_in=expiry
            )

            signed_url = response.get("signedURL")
            if not signed_url:
                raise ValueError("Failed to generate signed URL")

            logger.debug(f"Generated signed URL for {file_path} (expires in {expiry}s)")
            return signed_url

        except Exception as e:
            logger.error(f"Failed to generate signed URL: {e}")
            raise

    async def delete_file(self, file_path: str, bucket: Optional[str] = None) -> bool:
        """Delete a file from storage.

        Args:
            file_path: Path within bucket
            bucket: Bucket name (default: collections bucket)

        Returns:
            True if successful

        Raises:
            Exception: If deletion fails
        """
        try:
            bucket_name = bucket or self.collections_bucket
            self.client.storage.from_(bucket_name).remove([file_path])
            logger.info(f"Deleted file from storage: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete file from storage: {e}")
            raise

    async def delete_thread_images(self, user_id: str, thread_id: str) -> int:
        """Delete all images associated with a thread.

        Args:
            user_id: UUID of the user
            thread_id: UUID of the thread

        Returns:
            Number of files deleted

        Raises:
            Exception: If deletion fails
        """
        try:
            # List all files in the thread folder
            # Path format: {user_id}/{thread_id}/
            prefix = f"{user_id}/{thread_id}/"

            # List files with this prefix
            response = self.client.storage.from_(self.chat_uploads_bucket).list(
                path=f"{user_id}/{thread_id}"
            )

            if not response:
                logger.info(f"No files found for thread {thread_id}")
                return 0

            # Extract file paths
            file_paths = [f"{prefix}{file['name']}" for file in response if file.get('name')]

            if not file_paths:
                logger.info(f"No files to delete for thread {thread_id}")
                return 0

            # Delete all files
            self.client.storage.from_(self.chat_uploads_bucket).remove(file_paths)
            logger.info(f"Deleted {len(file_paths)} files from thread {thread_id}")
            return len(file_paths)

        except Exception as e:
            logger.error(f"Failed to delete thread images for {thread_id}: {e}")
            # Don't raise - we still want to delete the thread even if storage cleanup fails
            return 0

    def parse_storage_uri(self, storage_uri: str) -> dict:
        """Parse a storage:// URI into components.

        Args:
            storage_uri: URI in format storage://bucket/path

        Returns:
            dict with bucket and file_path

        Raises:
            ValueError: If URI format is invalid
        """
        if not storage_uri.startswith("storage://"):
            raise ValueError(f"Invalid storage URI format: {storage_uri}")

        # Remove storage:// prefix
        path = storage_uri[10:]

        # Split into bucket and file path
        parts = path.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid storage URI format: {storage_uri}")

        return {
            "bucket": parts[0],
            "file_path": parts[1]
        }

    async def get_file_url(self, storage_uri: str, signed: bool = True) -> str:
        """Get URL for a storage URI.

        Args:
            storage_uri: Storage URI (storage://bucket/path)
            signed: Whether to generate signed URL (default: True)

        Returns:
            URL string (signed or public)

        Raises:
            ValueError: If URI is invalid
            Exception: If URL generation fails
        """
        parsed = self.parse_storage_uri(storage_uri)

        if signed:
            return await self.get_signed_url(parsed["file_path"])
        else:
            # Return public URL
            return self.client.storage.from_(parsed["bucket"]).get_public_url(parsed["file_path"])


# Global service instance
storage_service = StorageService()
