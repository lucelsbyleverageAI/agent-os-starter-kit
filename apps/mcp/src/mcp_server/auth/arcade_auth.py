"""Arcade authentication and authorization management."""

import time
from typing import Dict, Optional

from ..config import settings
from ..utils.exceptions import AuthenticationError, AuthorizationError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ArcadeAuthManager:
    """Manages Arcade authentication and authorization for users."""

    def __init__(self) -> None:
        self._arcade_client: Optional[Arcade] = None
        self._auth_cache: Dict[str, Dict[str, any]] = {}
        # Add OAuth state tracking
        self._oauth_states: Dict[str, Dict[str, any]] = {}

    @property
    def arcade_client(self):
        """Get or create Arcade client instance."""
        if self._arcade_client is None:
            try:
                # Lazy import Arcade
                from arcadepy import Arcade
                
                self._arcade_client = Arcade(
                    api_key=settings.arcade_api_key,
                    base_url=settings.arcade_base_url,
                )
                # Test the connection
                self._arcade_client.health.check()
                logger.info("Arcade client initialized successfully")
            except ImportError as e:
                logger.error("Arcade library not available", error=str(e))
                raise AuthenticationError(f"Arcade library not installed: {str(e)}")
            except Exception as e:
                logger.error("Failed to initialize Arcade client", error=str(e))
                raise AuthenticationError(f"Failed to initialize Arcade client: {str(e)}")
        
        return self._arcade_client

    def check_user_authorization(self, user_id: str, tool_name: str) -> Optional[str]:
        """Check if user is authorized for a tool.
        
        Args:
            user_id: The user ID
            tool_name: The tool name to check authorization for
            
        Returns:
            Optional[str]: Authorization URL if authorization is needed, None if authorized
            
        Raises:
            AuthenticationError: If there's an authentication error
            AuthorizationError: If authorization is required
        """
        cache_key = f"{user_id}:{tool_name}"
        oauth_state_key = f"{user_id}:{tool_name}"
        
        # Check cache first
        if cache_key in self._auth_cache:
            cached_auth = self._auth_cache[cache_key]
            cache_age = time.time() - cached_auth["cached_at"]
            logger.info(
                "Found cached authorization", 
                user_id=user_id, 
                tool=tool_name,
                authorized=cached_auth["authorized"],
                cache_age_seconds=cache_age,
                cache_ttl=settings.user_auth_cache_ttl
            )
            if not self._is_auth_expired(cached_auth):
                if cached_auth["authorized"]:
                    logger.info("User authorized (cached)", user_id=user_id, tool=tool_name)
                    return None
                else:
                    # Check if we have a persistent OAuth state for this user/tool
                    if oauth_state_key in self._oauth_states:
                        oauth_state = self._oauth_states[oauth_state_key]
                        if not self._is_oauth_state_expired(oauth_state):
                            # Before reusing OAuth state, check if authorization was completed
                            if self._check_oauth_completion(user_id, tool_name, oauth_state):
                                logger.info("OAuth authorization completed, updating cache", user_id=user_id, tool=tool_name)
                                self._cache_auth_result(cache_key, True, None)
                                del self._oauth_states[oauth_state_key]
                                return None
                            
                            logger.info("Reusing existing OAuth state", user_id=user_id, tool=tool_name)
                            return oauth_state["auth_url"]
                    
                    logger.info("User not authorized (cached)", user_id=user_id, tool=tool_name)
                    return cached_auth.get("auth_url")
            else:
                logger.info("Cached authorization expired", user_id=user_id, tool=tool_name)

        # Check if we have a valid OAuth state before creating a new one
        if oauth_state_key in self._oauth_states:
            oauth_state = self._oauth_states[oauth_state_key]
            if not self._is_oauth_state_expired(oauth_state):
                # Check if authorization was completed since last check
                if self._check_oauth_completion(user_id, tool_name, oauth_state):
                    logger.info("OAuth authorization completed, updating cache", user_id=user_id, tool=tool_name)
                    self._cache_auth_result(cache_key, True, None)
                    del self._oauth_states[oauth_state_key]
                    return None
                
                logger.info("Reusing existing OAuth state", user_id=user_id, tool=tool_name)
                # Update cache with existing auth URL
                self._cache_auth_result(cache_key, False, oauth_state["auth_url"])
                return oauth_state["auth_url"]
            else:
                logger.info("OAuth state expired, removing", user_id=user_id, tool=tool_name)
                del self._oauth_states[oauth_state_key]

        # Check authorization with Arcade (this will generate a new state)
        try:
            logger.info(
                "Checking authorization with Arcade", 
                user_id=user_id, 
                tool=tool_name
            )
            auth_response = self.arcade_client.tools.authorize(
                tool_name=tool_name, 
                user_id=user_id
            )
            
            logger.info(
                "Arcade authorization response", 
                user_id=user_id, 
                tool=tool_name,
                status=auth_response.status,
                has_url=bool(auth_response.url)
            )
            
            if auth_response.status == "completed":
                # User is authorized
                self._cache_auth_result(cache_key, True, None)
                # Remove any OAuth state since authorization is complete
                if oauth_state_key in self._oauth_states:
                    del self._oauth_states[oauth_state_key]
                logger.info("User authorized for tool", user_id=user_id, tool=tool_name)
                return None
            else:
                # Authorization required - store the OAuth state
                auth_url = auth_response.url
                self._cache_auth_result(cache_key, False, auth_url)
                
                # Store OAuth state for reuse
                self._oauth_states[oauth_state_key] = {
                    "auth_url": auth_url,
                    "created_at": time.time(),
                    "status": auth_response.status,
                    "last_checked": time.time()
                }
                
                logger.info(
                    "User authorization required", 
                    user_id=user_id, 
                    tool=tool_name,
                    auth_url=auth_url,
                    status=auth_response.status
                )
                return auth_url
                
        except Exception as e:
            # Handle Arcade-specific exceptions with lazy import
            is_arcade_auth_error = False
            try:
                from arcadepy._exceptions import AuthenticationError as ArcadeAuthError
                from arcadepy._exceptions import PermissionDeniedError
                if isinstance(e, (ArcadeAuthError, PermissionDeniedError)):
                    is_arcade_auth_error = True
            except ImportError:
                # If arcadepy not available, treat as generic error
                pass
                
            if is_arcade_auth_error:
                logger.warning(
                    "Arcade authorization check failed", 
                    user_id=user_id, 
                    tool=tool_name,
                    error=str(e)
                )
            # Check if we have a stored OAuth state to reuse
            if oauth_state_key in self._oauth_states:
                oauth_state = self._oauth_states[oauth_state_key]
                if not self._is_oauth_state_expired(oauth_state):
                    # Check if authorization was completed
                    if self._check_oauth_completion(user_id, tool_name, oauth_state):
                        logger.info("OAuth authorization completed after error, updating cache", user_id=user_id, tool=tool_name)
                        self._cache_auth_result(cache_key, True, None)
                        del self._oauth_states[oauth_state_key]
                        return None
                    
                    logger.info("Reusing stored OAuth state after error", user_id=user_id, tool=tool_name)
                    self._cache_auth_result(cache_key, False, oauth_state["auth_url"])
                    return oauth_state["auth_url"]
            
            # Try to get authorization URL as fallback
            try:
                auth_response = self.arcade_client.tools.authorize(
                    tool_name=tool_name, 
                    user_id=user_id
                )
                auth_url = auth_response.url
                self._cache_auth_result(cache_key, False, auth_url)
                
                # Store new OAuth state
                self._oauth_states[oauth_state_key] = {
                    "auth_url": auth_url,
                    "created_at": time.time(),
                    "status": auth_response.status,
                    "last_checked": time.time()
                }
                
                return auth_url
            except Exception as inner_e:
                logger.error(
                    "Failed to get authorization URL", 
                    user_id=user_id, 
                    tool=tool_name,
                    error=str(inner_e)
                )
                raise AuthorizationError(
                    f"Authorization required for tool '{tool_name}' but failed to get auth URL"
                )
        except Exception as e:
            logger.error(
                "Unexpected error during authorization check", 
                user_id=user_id, 
                tool=tool_name,
                error=str(e)
            )
            raise AuthenticationError(f"Authorization check failed: {str(e)}")

    def _check_oauth_completion(self, user_id: str, tool_name: str, oauth_state: Dict) -> bool:
        """Check if OAuth authorization has been completed.
        
        This method checks with Arcade to see if the user has completed
        the OAuth flow since the last check.
        
        Args:
            user_id: The user ID
            tool_name: The tool name
            oauth_state: The stored OAuth state
            
        Returns:
            bool: True if authorization is now complete, False otherwise
        """
        # Only check completion if enough time has passed since last check
        # to avoid excessive API calls
        min_check_interval = 10  # seconds
        last_checked = oauth_state.get("last_checked", 0)
        time_since_check = time.time() - last_checked
        
        if time_since_check < min_check_interval:
            logger.debug(
                "Skipping OAuth completion check (too recent)", 
                user_id=user_id, 
                tool=tool_name,
                time_since_check=time_since_check
            )
            return False
        
        try:
            logger.info(
                "Checking OAuth completion status", 
                user_id=user_id, 
                tool=tool_name
            )
            
            # Update last checked time
            oauth_state["last_checked"] = time.time()
            
            # Check current authorization status
            auth_response = self.arcade_client.tools.authorize(
                tool_name=tool_name, 
                user_id=user_id
            )
            
            if auth_response.status == "completed":
                logger.info(
                    "OAuth authorization completed", 
                    user_id=user_id, 
                    tool=tool_name
                )
                return True
            else:
                logger.debug(
                    "OAuth authorization still pending", 
                    user_id=user_id, 
                    tool=tool_name,
                    status=auth_response.status
                )
                return False
                
        except Exception as e:
            logger.warning(
                "Failed to check OAuth completion", 
                user_id=user_id, 
                tool=tool_name,
                error=str(e)
            )
            return False

    def execute_tool(self, user_id: str, tool_name: str, tool_input: Dict, user_email: Optional[str] = None) -> Dict:
        """Execute an Arcade tool for a user.
        
        Args:
            user_id: The user ID
            tool_name: The tool name to execute
            tool_input: The tool input parameters
            user_email: Optional user email (preferred for Arcade authorization)
            
        Returns:
            Dict: The tool execution result
            
        Raises:
            AuthorizationError: If authorization is required
            ToolExecutionError: If tool execution fails
        """
        # Use email as user identifier if available, as Arcade works better with emails
        arcade_user_id = user_email if user_email else user_id
        
        # Check authorization first
        auth_url = self.check_user_authorization(arcade_user_id, tool_name)
        if auth_url:
            raise AuthorizationError(
                f"Authorization required for tool '{tool_name}'",
                auth_url=auth_url
            )

        # Execute the tool
        try:
            logger.info(
                "Executing Arcade tool", 
                user_id=user_id, 
                arcade_user_id=arcade_user_id,
                tool=tool_name,
                input_keys=list(tool_input.keys())
            )
            
            response = self.arcade_client.tools.execute(
                tool_name=tool_name,
                input=tool_input,
                user_id=arcade_user_id
            )
            
            if response.success and response.output:
                result = response.output.value
                logger.info(
                    "Tool execution successful", 
                    user_id=user_id, 
                    tool=tool_name
                )
                return result
            else:
                error_msg = "Unknown error"
                if response.output and response.output.error:
                    error_msg = str(response.output.error.message)
                
                logger.error(
                    "Tool execution failed", 
                    user_id=user_id, 
                    tool=tool_name,
                    error=error_msg
                )
                raise Exception(error_msg)
                
        except Exception as e:
            # Handle Arcade-specific exceptions with lazy import
            is_arcade_auth_error = False
            try:
                from arcadepy._exceptions import AuthenticationError as ArcadeAuthError
                from arcadepy._exceptions import PermissionDeniedError
                if isinstance(e, (ArcadeAuthError, PermissionDeniedError)):
                    is_arcade_auth_error = True
            except ImportError:
                # If arcadepy not available, treat as generic error
                pass
                
            if is_arcade_auth_error:
                # Authorization issue during execution
                logger.warning(
                    "Authorization error during tool execution", 
                    user_id=user_id, 
                    tool=tool_name,
                    error=str(e)
                )
                # Instead of invalidating cache, check if we have a valid OAuth state
                oauth_state_key = f"{arcade_user_id}:{tool_name}"
                if oauth_state_key in self._oauth_states:
                    oauth_state = self._oauth_states[oauth_state_key]
                    if not self._is_oauth_state_expired(oauth_state):
                        logger.info("Reusing OAuth state after execution error", user_id=arcade_user_id, tool=tool_name)
                        raise AuthorizationError(
                            f"Authorization required for tool '{tool_name}'",
                            auth_url=oauth_state["auth_url"]
                        )
                
                # Only invalidate cache and get new auth URL if no valid OAuth state exists
                self.invalidate_auth_cache(arcade_user_id, tool_name)
                auth_url = self.check_user_authorization(arcade_user_id, tool_name)
                raise AuthorizationError(
                    f"Authorization required for tool '{tool_name}'",
                    auth_url=auth_url
                )
            else:
                # Not an Arcade auth error, re-raise as-is
                raise
        except Exception as e:
            logger.error(
                "Tool execution error", 
                user_id=user_id, 
                tool=tool_name,
                error=str(e)
            )
            raise

    def _cache_auth_result(self, cache_key: str, authorized: bool, auth_url: Optional[str]) -> None:
        """Cache authorization result."""
        self._auth_cache[cache_key] = {
            "authorized": authorized,
            "auth_url": auth_url,
            "cached_at": time.time(),
        }

    def _is_auth_expired(self, cached_auth: Dict) -> bool:
        """Check if cached authorization has expired."""
        cache_age = time.time() - cached_auth["cached_at"]
        return cache_age > settings.user_auth_cache_ttl

    def _is_oauth_state_expired(self, oauth_state: Dict) -> bool:
        """Check if OAuth state has expired."""
        # OAuth states should have a longer TTL than auth cache
        # since they represent pending authorizations
        oauth_ttl = settings.user_auth_cache_ttl * 3  # 3x longer than auth cache
        state_age = time.time() - oauth_state["created_at"]
        return state_age > oauth_ttl

    def invalidate_auth_cache(self, user_id: str, tool_name: Optional[str] = None) -> None:
        """Invalidate authorization cache for a user and optionally a specific tool."""
        if tool_name:
            cache_key = f"{user_id}:{tool_name}"
            oauth_state_key = f"{user_id}:{tool_name}"
            
            # Remove from auth cache
            if cache_key in self._auth_cache:
                del self._auth_cache[cache_key]
                logger.info("Invalidated auth cache", user_id=user_id, tool=tool_name)
            
            # Remove from OAuth states (only if explicitly requested)
            if oauth_state_key in self._oauth_states:
                del self._oauth_states[oauth_state_key]
                logger.info("Invalidated OAuth state", user_id=user_id, tool=tool_name)
        else:
            # Invalidate all cache entries for the user
            auth_keys_to_remove = [
                key for key in self._auth_cache.keys() 
                if key.startswith(f"{user_id}:")
            ]
            oauth_keys_to_remove = [
                key for key in self._oauth_states.keys() 
                if key.startswith(f"{user_id}:")
            ]
            
            for key in auth_keys_to_remove:
                del self._auth_cache[key]
            for key in oauth_keys_to_remove:
                del self._oauth_states[key]
                
            logger.info(
                "Invalidated all cache for user", 
                user_id=user_id, 
                auth_count=len(auth_keys_to_remove),
                oauth_count=len(oauth_keys_to_remove)
            )

    def cleanup_expired_auth_cache(self) -> None:
        """Clean up expired authorization cache entries."""
        expired_auth_keys = [
            key for key, cached_auth in self._auth_cache.items()
            if self._is_auth_expired(cached_auth)
        ]
        
        expired_oauth_keys = [
            key for key, oauth_state in self._oauth_states.items()
            if self._is_oauth_state_expired(oauth_state)
        ]
        
        for key in expired_auth_keys:
            del self._auth_cache[key]
        for key in expired_oauth_keys:
            del self._oauth_states[key]
            
        if expired_auth_keys or expired_oauth_keys:
            logger.info(
                "Cleaned up expired cache", 
                auth_count=len(expired_auth_keys),
                oauth_count=len(expired_oauth_keys)
            )

    def check_authorization_status_only(self, user_id: str, tool_name: str) -> Dict[str, any]:
        """Check authorization status without generating new OAuth states.
        
        This method only checks existing cache and OAuth states without
        making new authorization requests to Arcade.
        
        Args:
            user_id: The user ID
            tool_name: The tool name to check authorization for
            
        Returns:
            Dict containing authorization status information
        """
        cache_key = f"{user_id}:{tool_name}"
        oauth_state_key = f"{user_id}:{tool_name}"
        
        result = {
            "user_id": user_id,
            "tool_name": tool_name,
            "authorized": False,
            "has_cached_auth": False,
            "has_oauth_state": False,
            "cache_expired": False,
            "oauth_state_expired": False,
            "auth_url": None
        }
        
        # Check auth cache
        if cache_key in self._auth_cache:
            cached_auth = self._auth_cache[cache_key]
            result["has_cached_auth"] = True
            result["cache_expired"] = self._is_auth_expired(cached_auth)
            
            if not result["cache_expired"]:
                result["authorized"] = cached_auth["authorized"]
                if not result["authorized"]:
                    result["auth_url"] = cached_auth.get("auth_url")
        
        # Check OAuth state
        if oauth_state_key in self._oauth_states:
            oauth_state = self._oauth_states[oauth_state_key]
            result["has_oauth_state"] = True
            result["oauth_state_expired"] = self._is_oauth_state_expired(oauth_state)
            
            if not result["oauth_state_expired"] and not result["authorized"]:
                result["auth_url"] = oauth_state["auth_url"]
        
        return result

    def debug_authorization_status(self, user_id: str, tool_name: str) -> Dict:
        """Debug method to check authorization status without caching."""
        try:
            logger.info("Debug: Checking raw authorization status", user_id=user_id, tool=tool_name)
            auth_response = self.arcade_client.tools.authorize(
                tool_name=tool_name, 
                user_id=user_id
            )
            
            # Also include OAuth state info
            oauth_state_key = f"{user_id}:{tool_name}"
            oauth_state_info = None
            if oauth_state_key in self._oauth_states:
                oauth_state = self._oauth_states[oauth_state_key]
                oauth_state_info = {
                    "has_stored_state": True,
                    "state_age": time.time() - oauth_state["created_at"],
                    "state_expired": self._is_oauth_state_expired(oauth_state),
                    "stored_url": oauth_state["auth_url"]
                }
            
            return {
                "user_id": user_id,
                "tool_name": tool_name,
                "status": auth_response.status,
                "has_url": bool(auth_response.url),
                "url": auth_response.url if auth_response.url else None,
                "oauth_state_info": oauth_state_info
            }
        except Exception as e:
            logger.error("Debug authorization check failed", user_id=user_id, tool=tool_name, error=str(e))
            return {
                "user_id": user_id,
                "tool_name": tool_name,
                "error": str(e)
            }


# Global Arcade auth manager instance
arcade_auth_manager = ArcadeAuthManager() 