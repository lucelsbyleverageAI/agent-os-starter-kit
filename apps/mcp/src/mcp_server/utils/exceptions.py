"""Custom exceptions for the MCP server."""

from typing import Any, Dict, Optional


class MCPServerError(Exception):
    """Base exception for MCP server errors."""

    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None, 
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}


class AuthenticationError(MCPServerError):
    """Authentication related errors."""

    def __init__(
        self, 
        message: str = "Authentication failed", 
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message, "AUTH_ERROR", context)


class AuthorizationError(MCPServerError):
    """Authorization related errors."""

    def __init__(
        self, 
        message: str = "Authorization required", 
        auth_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        context = context or {}
        if auth_url:
            context["auth_url"] = auth_url
        super().__init__(message, "AUTH_REQUIRED", context)


class ToolNotFoundError(MCPServerError):
    """Tool not found errors."""

    def __init__(
        self, 
        tool_name: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        message = f"Tool '{tool_name}' not found"
        super().__init__(message, "TOOL_NOT_FOUND", context)


class ToolExecutionError(MCPServerError):
    """Tool execution errors."""

    def __init__(
        self, 
        tool_name: str, 
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        message = f"Tool '{tool_name}' execution failed: {error_message}"
        super().__init__(message, "TOOL_EXECUTION_ERROR", context)


class ArcadeAPIError(MCPServerError):
    """Arcade API related errors."""

    def __init__(
        self, 
        message: str, 
        status_code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        context = context or {}
        if status_code:
            context["status_code"] = status_code
        super().__init__(message, "ARCADE_API_ERROR", context)


class ConfigurationError(MCPServerError):
    """Configuration related errors."""

    def __init__(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message, "CONFIG_ERROR", context)


class ValidationError(MCPServerError):
    """Input validation errors."""

    def __init__(
        self, 
        message: str, 
        field: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        context = context or {}
        if field:
            context["field"] = field
        super().__init__(message, "VALIDATION_ERROR", context) 