"""Base utilities for NHS Analytics toolkit.

Provides database connectivity, storage integration, and sandbox helper code.
"""

import os
from typing import Optional, Tuple, Type, Union
from ...config import settings
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

logger = get_logger(__name__)


def get_nhs_database_url(for_external_sandbox: bool = False) -> str:
    """Get NHS database connection string.

    Args:
        for_external_sandbox: If True, returns URL accessible from outside Docker (E2B sandboxes).
                             If False, returns URL for internal Docker network (MCP server).

    Returns:
        PostgreSQL connection string for NHS performance_data schema

    Raises:
        ToolExecutionError: If database configuration is missing
    """
    # Check for explicit NHS database URL first
    db_url = os.getenv("NHS_DATABASE_URL")

    if db_url:
        # If explicit URL provided and we need external access, replace internal Docker host
        if for_external_sandbox and "db:5432" in db_url:
            db_url = db_url.replace("db:5432", "host.docker.internal:5432")
            logger.info("NHS database URL adapted for external sandbox", host="host.docker.internal:5432")
        else:
            logger.info("Using configured NHS database URL",
                       context="external_sandbox" if for_external_sandbox else "internal")
        return db_url

    # Fall back to constructing from environment variables
    db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_name = os.getenv("POSTGRES_DB", "postgres")
    db_port = os.getenv("POSTGRES_PORT", "5432")

    # Choose host based on context
    if for_external_sandbox:
        # E2B sandboxes run outside Docker network, need host.docker.internal for local dev
        # or public URL for production
        db_host = "host.docker.internal"
        logger.info("Constructed NHS database URL for external sandbox", host=db_host)
    else:
        # MCP server runs inside Docker, use Docker service name
        db_host = "db"
        logger.info("Constructed NHS database URL for internal Docker network", host=db_host)

    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return db_url


def get_sandbox_helper_code() -> str:
    """Get minimal Python code to establish database connection in E2B sandbox.

    Returns:
        Python code as a string to be executed in sandbox initialization
    """
    return """
# NHS Analytics Sandbox - Database Connection Setup
import os
from sqlalchemy import create_engine

# NHS Database Configuration (from environment variables)
NHS_DB_URL = os.environ.get('NHS_DB_URL')
NHS_SCHEMA = os.environ.get('NHS_SCHEMA', 'performance_data')

# Create database engine
db_engine = create_engine(NHS_DB_URL)

print(f"✅ Database connection established")
print(f"Database schema: {NHS_SCHEMA}")
print(f"Use 'db_engine' to execute queries with pandas: pd.read_sql(query, db_engine)")
"""


def get_sandbox_config() -> Tuple[str, str, str]:
    """Determine which sandbox type to use and corresponding database URL.

    Returns:
        Tuple of (sandbox_mode, database_url, network_name)
        - sandbox_mode: 'local' or 'e2b'
        - database_url: Database connection string appropriate for the sandbox
        - network_name: Docker network name (only used for local mode)

    Raises:
        ToolExecutionError: If configuration is invalid
    """
    sandbox_mode = settings.sandbox_mode.lower()
    environment = settings.environment.lower()

    # Auto-detect mode
    if sandbox_mode == "auto":
        # Use local sandbox for development, E2B for production/staging
        if environment in ["development", "local"]:
            sandbox_mode = "local"
            logger.info("Auto-detected sandbox mode: local (development environment)")
        else:
            sandbox_mode = "e2b"
            logger.info("Auto-detected sandbox mode: e2b (production/staging environment)")

    # Validate mode
    if sandbox_mode not in ["local", "e2b"]:
        raise ToolExecutionError(
            "sandbox_config",
            f"Invalid sandbox_mode: {sandbox_mode}. Must be 'local', 'e2b', or 'auto'"
        )

    # Get database URL based on sandbox type
    if sandbox_mode == "local":
        # Local Docker sandbox can access internal Docker network
        db_url = get_nhs_database_url(for_external_sandbox=False)
        network_name = settings.docker_network_name
        logger.info(
            "Using local Docker sandbox",
            db_url_preview=db_url[:30] + "...",
            network=network_name
        )
    else:  # e2b
        # E2B sandboxes need external/public database URL
        db_url = get_nhs_database_url(for_external_sandbox=True)
        network_name = ""  # Not used for E2B
        logger.info(
            "Using E2B cloud sandbox",
            db_url_preview=db_url[:30] + "..."
        )

        # Validate E2B API key
        if not settings.e2b_api_key:
            raise ToolExecutionError(
                "sandbox_config",
                "E2B API key not configured. Set E2B_API_KEY or use SANDBOX_MODE=local"
            )

    return sandbox_mode, db_url, network_name


def get_sandbox_class() -> Union[Type, Type]:
    """Get the appropriate sandbox class based on configuration.

    Returns:
        Sandbox class (either DockerLocalSandbox or AsyncSandbox from E2B)

    Raises:
        ToolExecutionError: If sandbox mode is invalid or dependencies missing
    """
    sandbox_mode, _, _ = get_sandbox_config()

    if sandbox_mode == "local":
        try:
            from .docker_sandbox import DockerLocalSandbox
            return DockerLocalSandbox
        except ImportError as e:
            raise ToolExecutionError(
                "sandbox_config",
                f"Failed to import DockerLocalSandbox. Is docker package installed? {e}"
            )
    else:  # e2b
        try:
            from e2b_code_interpreter import AsyncSandbox
            return AsyncSandbox
        except ImportError as e:
            raise ToolExecutionError(
                "sandbox_config",
                f"Failed to import E2B AsyncSandbox. Is e2b_code_interpreter installed? {e}"
            )


class NHSStorageClient:
    """Client for uploading NHS analytics outputs to Supabase storage."""

    BUCKET_NAME = "nhs-analytics-outputs"

    def __init__(self):
        """Initialize storage client."""
        self.supabase_url = settings.supabase_url
        self.supabase_service_key = settings.supabase_service_key

        if not self.supabase_url or not self.supabase_service_key:
            logger.warning("Supabase storage not configured - file uploads will fail")

    async def upload_visualization(
        self,
        user_id: str,
        filename: str,
        file_bytes: bytes,
        content_type: str = "image/png"
    ) -> str:
        """Upload visualization file to Supabase storage.

        Args:
            user_id: User ID for folder organization
            filename: Name of the file (with extension)
            file_bytes: File content as bytes
            content_type: MIME type (default: image/png)

        Returns:
            Signed URL for the uploaded file (1 hour expiry)

        Raises:
            ToolExecutionError: If upload or URL generation fails
        """
        try:
            from supabase import create_client

            # Check configuration
            if not self.supabase_url or not self.supabase_service_key:
                raise ToolExecutionError(
                    "nhs_analytics",
                    "Supabase storage not configured. Contact administrator."
                )

            # Create Supabase client
            supabase = create_client(
                self.supabase_url,
                self.supabase_service_key
            )

            # Upload file to user's folder
            storage_path = f"{user_id}/{filename}"

            supabase.storage.from_(self.BUCKET_NAME).upload(
                path=storage_path,
                file=file_bytes,
                file_options={
                    "content-type": content_type,
                    "cache-control": "3600",
                    "upsert": "true"  # Overwrite if exists
                }
            )

            logger.info(
                "Uploaded visualization to storage",
                bucket=self.BUCKET_NAME,
                path=storage_path,
                size_bytes=len(file_bytes)
            )

            # Generate signed URL (1 hour expiry)
            response = supabase.storage.from_(self.BUCKET_NAME).create_signed_url(
                path=storage_path,
                expires_in=3600
            )

            signed_url = response.get("signedURL")

            if not signed_url:
                raise ToolExecutionError(
                    "nhs_analytics",
                    "Failed to generate download URL from storage"
                )

            # Fix URL for development environment (Kong proxy)
            if os.getenv("ENVIRONMENT", "development") == "development":
                signed_url = signed_url.replace("kong:8000", "localhost:8000")

            logger.info("Generated signed URL for visualization", url_preview=signed_url[:50])
            return signed_url

        except Exception as e:
            logger.error(f"Failed to upload to storage: {e}", exc_info=True)
            raise ToolExecutionError(
                "nhs_analytics",
                f"Failed to upload file to storage: {str(e)}"
            )
