"""Auth to resolve user or service account object."""

from typing import Annotated, Union, Any

from fastapi import Depends
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.authentication import BaseUser
from supabase import create_client

from langconnect import config

security = HTTPBearer()


class AuthenticatedUser(BaseUser):
    """An authenticated user following the Starlette authentication model."""

    def __init__(self, user_id: str, display_name: str) -> None:
        """Initialize the AuthenticatedUser.

        Args:
            user_id: Unique identifier for the user.
            display_name: Display name for the user.
        """
        self.user_id = user_id
        self._display_name = display_name

    @property
    def is_authenticated(self) -> bool:
        """Return True if the user is authenticated."""
        return True

    @property
    def display_name(self) -> str:
        """Return the display name of the user."""
        return self._display_name

    @property
    def identity(self) -> str:
        """Return the identity of the user. This is a unique identifier."""
        return self.user_id

    @property
    def actor_type(self) -> str:
        """Return the actor type for activity logging."""
        return "user"


class ServiceAccount(BaseUser):
    """A service account for external system authentication (n8n, Zapier, etc.)."""

    def __init__(self, service_id: str = "system_service") -> None:
        """Initialize the ServiceAccount.

        Args:
            service_id: Identifier for the service account.
        """
        self.service_id = service_id
        self._display_name = "System Service"

    @property
    def is_authenticated(self) -> bool:
        """Return True if the service account is authenticated."""
        return True

    @property
    def display_name(self) -> str:
        """Return the display name of the service account."""
        return self._display_name

    @property
    def identity(self) -> str:
        """Return the identity of the service account."""
        return self.service_id

    @property
    def actor_type(self) -> str:
        """Return the actor type for activity logging."""
        return "service"

    @property
    def is_admin(self) -> bool:
        """Service accounts have admin privileges."""
        return True

    def requires_owner_assignment(self) -> bool:
        """Service accounts must specify owner when creating resources."""
        return True


# Type alias for authentication result
AuthenticatedActor = Union[AuthenticatedUser, ServiceAccount]


def get_current_user(authorization: str) -> Any:
    """Authenticate a user by validating their JWT token against Supabase.

    This function verifies the provided JWT token by making a request to Supabase.
    It requires the SUPABASE_URL and SUPABASE_KEY environment variables to be
    properly configured.

    Args:
        authorization: JWT token string to validate

    Returns:
        User: A Supabase User object containing the authenticated user's information

    Raises:
        HTTPException: With status code 500 if Supabase configuration is missing
        HTTPException: With status code 401 if token is invalid or authentication fails
    """
    try:
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        response = supabase.auth.get_user(authorization)
        
    except Exception as e:
        # Surface configuration errors clearly
        raise HTTPException(status_code=500, detail=f"Supabase validation error: {type(e).__name__}")
    user = response.user

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token or user not found")
    return user


def validate_service_account_key(api_key: str) -> bool:
    """Validate the service account API key.

    Args:
        api_key: The API key to validate

    Returns:
        bool: True if the API key is valid, False otherwise
    """
    if not config.SERVICE_ACCOUNT_KEY:
        return False
    return api_key == config.SERVICE_ACCOUNT_KEY


def resolve_user_or_service(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> AuthenticatedActor:
    """Resolve user or service account from the credentials.

    Supports both JWT tokens for users and static API keys for service accounts.

    Args:
        credentials: HTTP Authorization credentials

    Returns:
        AuthenticatedActor: Either an AuthenticatedUser or ServiceAccount

    Raises:
        HTTPException: If authentication fails
    """
    if credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    if not credentials.credentials:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check if it's a service account API key first
    if validate_service_account_key(credentials.credentials):
        return ServiceAccount()

    # Handle testing mode for users
    if config.IS_TESTING:
        if credentials.credentials in {"user1", "user2"}:
            return AuthenticatedUser(credentials.credentials, credentials.credentials)
        raise HTTPException(
            status_code=401, detail="Invalid credentials or user not found"
        )

    # Try JWT authentication for regular users
    try:
        user = get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return AuthenticatedUser(user.id, user.user_metadata.get("name", "User"))
    except Exception as e:
        # If JWT validation fails, it might be an invalid API key or token
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials - neither valid JWT token nor service API key"
        )


def resolve_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> AuthenticatedUser:
    """Resolve authenticated user from JWT token (service accounts not allowed).

    This function is used for endpoints that are user-specific and should not
    be accessible to service accounts (e.g., user default assistant settings).

    Args:
        credentials: HTTP Authorization credentials with JWT token

    Returns:
        AuthenticatedUser: The authenticated user

    Raises:
        HTTPException: If authentication fails or service account is used
    """
    if credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    if not credentials.credentials:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Reject service account API keys for user-only endpoints
    if validate_service_account_key(credentials.credentials):
        raise HTTPException(
            status_code=403,
            detail="Service accounts cannot access user-specific endpoints"
        )

    # Handle testing mode for users
    if config.IS_TESTING:
        if credentials.credentials in {"user1", "user2"}:
            return AuthenticatedUser(credentials.credentials, credentials.credentials)
        raise HTTPException(
            status_code=401, detail="Invalid credentials or user not found"
        )

    # Try JWT authentication for regular users
    try:
        user = get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return AuthenticatedUser(user.id, user.user_metadata.get("name", "User"))
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials - must provide valid JWT token"
        )


