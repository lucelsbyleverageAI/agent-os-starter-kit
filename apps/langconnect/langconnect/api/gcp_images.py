"""GCP Images API router for generating signed URLs."""

import logging
import os
from typing import Optional
import base64

from fastapi import APIRouter, HTTPException, Query
from google.cloud import storage
from google.cloud.exceptions import NotFound
from google.oauth2 import service_account
import json
import sentry_sdk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gcp", tags=["gcp"])


def get_gcp_storage_client():
    """Get GCP Storage client using environment credentials."""
    try:
        project_id = os.getenv("GCP_PROJECT_ID")
        if not project_id:
            raise ValueError("GCP_PROJECT_ID environment variable is required")
        
        # Try base64 encoded service account key first (for production)
        service_account_key_b64 = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
        if service_account_key_b64:
            try:
                # Decode base64 and parse JSON
                service_account_key_json = base64.b64decode(service_account_key_b64).decode('utf-8')
                credentials_info = json.loads(service_account_key_json)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info
                )
                logger.info("GCP Storage client initialized from base64 service account key")
                return storage.Client(project=project_id, credentials=credentials)
            except Exception as e:
                logger.error(f"Failed to parse base64 service account key: {str(e)}")
                raise ValueError(f"Invalid base64 service account key: {str(e)}")
        
        # Try credentials JSON string (for direct JSON env vars)
        credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
        if credentials_json:
            credentials_info = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info
            )
            logger.info("GCP Storage client initialized from JSON credentials")
            return storage.Client(project=project_id, credentials=credentials)
        
        # Try credentials file path (for local development)
        credentials_path = os.getenv("GCP_CREDENTIALS_PATH")
        if credentials_path and os.path.exists(credentials_path):
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            logger.info("GCP Storage client initialized from credentials file")
            return storage.Client(project=project_id, credentials=credentials)
        
        # Try default credentials (for GCP environments)
        logger.info("GCP Storage client initialized with default credentials")
        return storage.Client(project=project_id)
        
    except Exception as e:
        logger.error(f"Failed to initialize GCP Storage client: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"GCP configuration error: {str(e)}"
        )


def generate_signed_url(filename: str, expiry_hours: int = 24) -> str:
    """Generate signed URL for GCP-stored file."""
    try:
        client = get_gcp_storage_client()
        bucket_name = os.getenv("GCP_STORAGE_BUCKET")
        if not bucket_name:
            raise ValueError("GCP_STORAGE_BUCKET environment variable is required")
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(filename)
        
        # Check if file exists
        if not blob.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {filename}"
            )
        
        # Check if public access is enabled
        public_access = os.getenv("IMAGE_PUBLIC_ACCESS", "false").lower() == "true"
        if public_access:
            # Return public URL
            base_url = os.getenv("IMAGE_BASE_URL") or f"https://storage.googleapis.com/{bucket_name}"
            return f"{base_url}/{filename}"
        
        # Generate signed URL
        from datetime import datetime, timedelta
        expiry_time = datetime.utcnow() + timedelta(hours=expiry_hours)
        
        signed_url = blob.generate_signed_url(
            expiration=expiry_time,
            method="GET"
        )
        
        return signed_url
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to generate signed URL for {filename}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate signed URL: {str(e)}"
        )


@router.get("/signed-url")
async def get_signed_url(
    filename: str = Query(..., description="GCP storage filename/path for the image")
) -> dict:
    """
    Generate a signed URL for a GCP-stored image.
    
    Args:
        filename: The GCP storage path/filename (e.g., "images/user123/tool/image.png")
    
    Returns:
        Dictionary containing the signed URL and metadata
    """
    sentry_sdk.add_breadcrumb(
        category="api.request",
        data={
            "endpoint": "get_signed_url",
            "filename": filename
        },
        level="info"
    )
    
    try:
        # Validate filename
        if not filename:
            raise HTTPException(status_code=400, detail="Missing filename parameter")
        
        # Validate it's an image file
        image_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp']
        if not any(filename.lower().endswith(ext) for ext in image_extensions):
            raise HTTPException(
                status_code=400, 
                detail="File is not a supported image format"
            )
        
        # Get expiry hours from environment
        expiry_hours = int(os.getenv("IMAGE_URL_EXPIRY_HOURS", "24"))
        
        # Generate signed URL
        signed_url = generate_signed_url(filename, expiry_hours)
        
        logger.info(
            f"Generated signed URL for image: {filename} (expires in {expiry_hours}h)"
        )
        
        return {
            "url": signed_url,
            "filename": filename,
            "expires_in_hours": expiry_hours
        }
        
    except HTTPException:
        # Re-raise FastAPI HTTP exceptions
        raise
    except Exception as e:
        logger.error(
            f"Error generating signed URL for {filename}: {str(e)}", exc_info=True
        )
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        ) 