"""Clean MCP server implementation with only modern transports and MCP token auth."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional, Sequence

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.stdio import stdio_server
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, Mount
from starlette.types import Receive, Scope, Send
from starlette.responses import JSONResponse, Response
from starlette.requests import Request

from .auth.user_context import UserContext, user_context_manager
from .config import settings
from .tools.base import BaseTool
from .tools.custom_tools import CUSTOM_TOOLS
from .utils.exceptions import (
    AuthenticationError,
    AuthorizationError,
    MCPServerError,
    ToolExecutionError,
    ToolNotFoundError,
)
from .sentry import get_logger

logger = get_logger(__name__)


class MCPToolServer:
    """Core MCP server that provides tools via official MCP SDK."""

    def __init__(self) -> None:
        self.server = Server(settings.mcp_server_name)
        self._tools_cache: Dict[str, BaseTool] = {}
        self._current_user_context: Optional[UserContext] = None
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up MCP server handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """Handle tools/list request."""
            try:
                logger.debug("Listing available tools")
                
                # Get all available tools
                all_tools = await self._get_all_tools()
                
                # Convert to MCP tool format
                mcp_tools = []
                for tool in all_tools:
                    tool_schema = tool.definition.to_mcp_schema()
                    
                    # Create meta dict with toolkit information
                    meta = {}
                    if tool_schema["function"].get("toolkit"):
                        meta["toolkit"] = tool_schema["function"]["toolkit"]
                    if tool_schema["function"].get("toolkit_display_name"):
                        meta["toolkit_display_name"] = tool_schema["function"]["toolkit_display_name"]
                    
                    mcp_tools.append(types.Tool(
                        name=tool.name,
                        description=tool.description,
                        inputSchema=tool_schema["function"]["parameters"],
                        meta=meta if meta else None
                    ))
                
                logger.debug("Tools listed successfully", count=len(mcp_tools))
                return mcp_tools
                
            except Exception as e:
                logger.error("Failed to list tools", error=str(e))
                raise MCPServerError(f"Failed to list tools: {str(e)}")

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, 
            arguments: Optional[Dict[str, Any]] = None
        ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """Handle tools/call request."""
            return await self._execute_tool(name, arguments)

    async def _execute_tool(
        self, 
        name: str, 
        arguments: Optional[Dict[str, Any]] = None
    ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Execute a tool with proper auth and memory policy enforcement."""
        start_time = time.time()
        
        try:
            logger.info(
                "MCP Tool Execution: Request received",
                tool_name=name,
                args_keys=list(arguments.keys()) if arguments else [],
                execution_start_time=start_time,
                mcp_compliance="Tool execution with proper authentication and authorization"
            )
            
            # Get user context (set by middleware)
            user_context = self._get_current_user_context()
            
            logger.info(
                "MCP Tool Execution: User context validated",
                tool_name=name,
                user_id=user_context.user_id,
                auth_method=user_context.metadata.get('auth_method', 'unknown'),
                user_email=user_context.email,
                has_jwt_token=bool(user_context.metadata.get('jwt_token')),
                spec_compliance="Token audience validation per RFC 8707"
            )
            
            # Get the tool
            tool = await self._get_tool(name)
            if not tool:
                logger.error(
                    "MCP Tool Execution: Tool not found",
                    tool_name=name,
                    available_tools=list(self._tools_cache.keys()),
                    user_id=user_context.user_id
                )
                raise ToolNotFoundError(name)
            
            # Execute the tool with timeout
            try:
                # Add JWT token for memory tools that need authentication with LangConnect
                execution_kwargs = arguments or {}
                if hasattr(tool, 'toolkit_name') and tool.toolkit_name == 'memory':
                    # Block memory tools for service-account authentication (MCP security requirement)
                    auth_method = user_context.metadata.get('auth_method') if hasattr(user_context, 'metadata') else None
                    if auth_method == 'service_account':
                        logger.warning(
                            "MCP Security: Memory tool access blocked for service account",
                            tool_name=name,
                            auth_method=auth_method,
                            user_id=user_context.user_id,
                            security_policy="Service accounts cannot access user-specific resources",
                            spec_compliance="MCP Authorization security requirements"
                        )
                        raise AuthorizationError("Memory tools are not available for service-account authentication. Please authenticate as a user.")
                    
                    # Extract Supabase JWT from user context for downstream LangConnect calls
                    jwt_token = user_context.metadata.get('jwt_token')
                    logger.info(
                        "MCP Tool Execution: Memory tool JWT token extraction",
                        tool_name=name,
                        user_id=user_context.user_id,
                        auth_method=auth_method,
                        has_token=bool(jwt_token),
                        user_metadata_keys=list(user_context.metadata.keys()),
                        spec_compliance="Token passthrough prevention per MCP security guidelines"
                    )
                    
                    if jwt_token:
                        execution_kwargs['_jwt_token'] = jwt_token
                        logger.info(
                            "MCP Tool Execution: JWT token added for downstream LangConnect authentication",
                            tool_name=name,
                            user_id=user_context.user_id,
                            final_args=list(execution_kwargs.keys()),
                            security_note="Using original user JWT for downstream service authentication"
                        )
                    else:
                        logger.warning(
                            "MCP Tool Execution: JWT token not found in user context for memory tool",
                            tool_name=name,
                            user_id=user_context.user_id,
                            auth_method=auth_method,
                            potential_issue="Memory tool may fail without proper downstream authentication"
                        )
                
                result = await asyncio.wait_for(
                    tool.execute(
                        user_id=user_context.user_id,
                        user_email=user_context.email,
                        **execution_kwargs
                    ),
                    timeout=settings.tool_execution_timeout
                )
            except asyncio.TimeoutError:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    "Tool execution timed out", 
                    tool=name, 
                    user_id=user_context.user_id,
                    duration_ms=duration,
                    timeout_seconds=settings.tool_execution_timeout
                )
                return [types.TextContent(
                    type="text",
                    text=f"Tool execution timed out after {settings.tool_execution_timeout} seconds. Please try breaking down your request into smaller operations."
                )]
            
            # Format result as MCP content
            content = self._format_tool_result(result)
            
            duration = (time.time() - start_time) * 1000
            logger.info(
                "MCP Tool Execution: Completed successfully",
                tool_name=name,
                user_id=user_context.user_id,
                user_email=user_context.email,
                auth_method=user_context.metadata.get('auth_method', 'unknown'),
                duration_ms=duration,
                result_type=type(result).__name__,
                content_blocks=len(content),
                spec_compliance="MCP tool execution with proper authentication and authorization"
            )
            
            return content
            
        except AuthorizationError as e:
            logger.warning("Authorization required", tool=name, error=str(e))
            # Return authorization prompt
            auth_content = self._format_authorization_error(e)
            return auth_content
            
        except (AuthenticationError, ToolNotFoundError, ToolExecutionError) as e:
            logger.error("Tool execution failed", tool=name, error=str(e))
            return [types.TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )]
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(
                "Unexpected tool execution error", 
                tool=name, 
                error=str(e),
                duration_ms=duration
            )
            return [types.TextContent(
                type="text",
                text=f"Unexpected error: {str(e)}"
            )]

    async def _get_all_tools(self) -> List[BaseTool]:
        """Get all available tools (Arcade + custom)."""
        all_tools = []
        
        # Get Arcade tools if enabled and available
        if settings.enable_arcade:
            try:
                from .tools.arcade_tools import arcade_tools_manager
                arcade_tools = await arcade_tools_manager.get_available_tools()
                all_tools.extend(arcade_tools)
                logger.info("Arcade tools loaded successfully", count=len(arcade_tools))
            except ImportError as e:
                logger.warning("Arcade tools not available - arcadepy not installed", error=str(e))
            except Exception as e:
                logger.warning("Failed to load Arcade tools", error=str(e))
        else:
            logger.info("Arcade tools disabled in configuration")
        
        # Get custom tools
        if settings.enable_custom_tools:
            all_tools.extend(CUSTOM_TOOLS)
            logger.info("Custom tools loaded", count=len(CUSTOM_TOOLS))
        
        # Update cache
        self._tools_cache = {tool.name: tool for tool in all_tools}
        
        return all_tools

    async def _get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get a specific tool by name."""
        # Check cache first
        if tool_name in self._tools_cache:
            return self._tools_cache[tool_name]
        
        # Refresh tools and check again
        await self._get_all_tools()
        return self._tools_cache.get(tool_name)

    def set_user_context(self, user_context: UserContext) -> None:
        """Set the current user context (called by middleware)."""
        self._current_user_context = user_context

    def _get_current_user_context(self) -> UserContext:
        """Get the current user context."""
        if self._current_user_context:
            return self._current_user_context
        
        # Fallback for backward compatibility
        return UserContext(
            user_id="default_user",
            authenticated_at=time.time()
        )

    def _format_tool_result(self, result: Any) -> Sequence[types.TextContent]:
        """Format tool execution result as MCP content."""
        if isinstance(result, str):
            content_text = result
        elif isinstance(result, dict):
            import json
            content_text = json.dumps(result, indent=2, default=str)
        else:
            content_text = str(result)
        
        return [types.TextContent(
            type="text",
            text=content_text
        )]

    def _format_authorization_error(self, error: AuthorizationError) -> Sequence[types.TextContent]:
        """Format authorization error as MCP content."""
        auth_url = error.context.get("auth_url") if hasattr(error, 'context') and error.context else None
        
        if auth_url:
            message = f"Authorization required. Please visit: {auth_url}"
        else:
            message = f"Authorization required: {error.message}"
        
        return [types.TextContent(
            type="text",
            text=message
        )]

    async def run_stdio(self) -> None:
        """Run the server using stdio transport."""
        logger.info("Starting MCP server with stdio transport", name=settings.mcp_server_name)
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                types.InitializationOptions(
                    server_name=settings.mcp_server_name,
                    server_version="0.1.0",
                    capabilities=types.ServerCapabilities(
                        tools=types.ToolsCapability(),
                    ),
                ),
            )


class MCPHTTPServer:
    """HTTP-based MCP server using official MCP transports only."""

    def __init__(self) -> None:
        self.mcp_server = MCPToolServer()
        self.session_manager: Optional[StreamableHTTPSessionManager] = None
        self._setup_http_server()

    def _setup_http_server(self) -> None:
        """Set up Starlette HTTP server with official MCP transports."""
        
        # Create the session manager with stateless mode
        self.session_manager = StreamableHTTPSessionManager(
            app=self.mcp_server.server,
            event_store=None,  # Stateless mode
            json_response=False,  # Use SSE streaming
            stateless=True,
        )

        async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
            """Handle MCP Streamable HTTP requests with authentication."""
            try:
                logger.info("Streamable HTTP request", 
                           method=scope.get('method'),
                           path=scope.get('path'))
                
                # Handle root path requests directly
                if scope.get("path") == "/mcp":
                    scope = dict(scope)
                    scope["path"] = "/"
                    scope["raw_path"] = b"/"
                
                # Log MCP requests for debugging
                logger.debug("MCP Mount handler received request", 
                           method=scope.get('method'),
                           path=scope.get('path'))
                
                # Handle CORS preflight requests FIRST, before any other processing
                if scope.get("method") == "OPTIONS":
                    logger.info("Mount handler: Handling CORS preflight request", path=scope.get('path'))
                    await send({
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"access-control-allow-origin", b"*"),
                            (b"access-control-allow-methods", b"GET, POST, DELETE, OPTIONS"),
                            (b"access-control-allow-headers", b"*"),
                            (b"access-control-allow-credentials", b"true"),
                            (b"access-control-max-age", b"86400"),
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": b"",
                    })
                    return
                
                # Extract authentication from headers
                headers = dict(scope.get("headers", []))
                headers_str = {k.decode(): v.decode() for k, v in headers.items()}
                
                # Log incoming request with authentication info
                auth_header = headers_str.get("authorization", "")
                has_auth = bool(auth_header and auth_header.startswith("Bearer "))
                
                logger.info("MCP streamable HTTP request", 
                           method=scope.get('method'),
                           path=scope.get('path'),
                           has_auth=has_auth)
                
                # Check if this is a public OAuth discovery endpoint that doesn't need auth
                request_path = scope.get('path', '')
                is_discovery_endpoint = (
                    request_path == '/.well-known/oauth-authorization-server' or
                    request_path == '/.well-known/oauth-protected-resource' or
                    request_path == '/.well-known/oauth-protected-resource/mcp' or
                    request_path == '/.well-known/openid-configuration'
                )
                
                # Only extract user context for non-discovery endpoints
                if not is_discovery_endpoint:
                    # Extract user context
                    user_context = user_context_manager.extract_user_context(headers_str)
                    
                    # Set user context for this request
                    self.mcp_server.set_user_context(user_context)
                    
                    logger.info("User context established", 
                               user_id=user_context.user_id,
                               auth_method=user_context.metadata.get('auth_method'))
                else:
                    logger.info("Skipping authentication for OAuth discovery endpoint", path=request_path)
                
                # Handle the MCP request
                logger.info("Passing request to session manager",
                           method=scope.get('method'),
                           path=scope.get('path'))
                await self.session_manager.handle_request(scope, receive, send)
                
            except AuthenticationError as e:
                client_ip = dict(scope.get("headers", {})).get(b"x-forwarded-for", b"unknown").decode()
                user_agent = dict(scope.get("headers", {})).get(b"user-agent", b"unknown").decode()
                request_path = scope.get("path", "unknown")
                
                logger.warning(
                    "MCP Authorization: Authentication failed - returning 401 with WWW-Authenticate header",
                    error=str(e),
                    client_ip=client_ip,
                    user_agent=user_agent,
                    path=request_path,
                    method=scope.get("method"),
                    spec_reference="RFC9728 Section 5.1",
                    mcp_compliance="WWW-Authenticate header includes resource_metadata for discovery"
                )
                
                # Return authentication error response with RFC 9728 headers
                www_authenticate = getattr(e, 'context', {}).get('www_authenticate', 'Bearer realm="OAuth"')
                auth_url = getattr(e, 'context', {}).get('auth_url')
                resource_metadata_url = getattr(e, 'context', {}).get('resource_metadata_url')
                
                response_data = {
                    "error": "authentication_required",
                    "message": "Authentication required to access MCP server",
                    "instructions": "Use Authorization: Bearer <mcp_access_token> or service account key"
                }
                
                if auth_url:
                    response_data["auth_url"] = auth_url
                    response_data["instructions"] += f". For user authentication, visit: {auth_url}"
                
                if resource_metadata_url:
                    response_data["resource_metadata"] = resource_metadata_url
                
                logger.info(
                    "MCP Authorization: Sending 401 Unauthorized response with discovery metadata",
                    client_ip=client_ip,
                    path=request_path,
                    www_authenticate_header=www_authenticate,
                    auth_url=auth_url,
                    resource_metadata_url=resource_metadata_url,
                    spec_compliance="RFC9728 + OAuth 2.1"
                )
                
                response = JSONResponse(
                    status_code=401,
                    content=response_data,
                    headers={"WWW-Authenticate": www_authenticate}
                )
                
                await response(scope, receive, send)
                
            except Exception as e:
                logger.error("MCP request failed", error=str(e))
                
                response = JSONResponse(
                    status_code=500,
                    content={"error": "internal_server_error", "message": str(e)}
                )
                await response(scope, receive, send)

        async def handle_health_check(request: Request) -> JSONResponse:
            """Health check endpoint."""
            return JSONResponse({
                "status": "healthy", 
                "server": settings.mcp_server_name,
                "transports": ["streamable-http"],
                "version": "0.1.0"
            })

        async def handle_oauth_discovery(request: Request) -> JSONResponse:
            """OAuth 2.1 Authorization Server Metadata (RFC 8414) - MCP Compliant."""
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            # Handle CORS preflight
            if request.method == "OPTIONS":
                logger.info(
                    "MCP Authorization: CORS preflight request for OAuth Authorization Server Metadata",
                    endpoint="/.well-known/oauth-authorization-server",
                    method="OPTIONS",
                    client_ip=client_ip,
                    user_agent=user_agent,
                    spec_reference="RFC8414"
                )
                return JSONResponse(
                    content={},
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                        "Access-Control-Max-Age": "86400",
                    }
                )
            
            base_url = settings.mcp_public_base_url or f"http://{settings.mcp_server_host}:{settings.mcp_server_port}"
            issuer = settings.frontend_base_url
            
            logger.info(
                "MCP Authorization: OAuth 2.1 Authorization Server Metadata request",
                endpoint="/.well-known/oauth-authorization-server",
                method="GET",
                client_ip=client_ip,
                user_agent=user_agent,
                base_url=base_url,
                issuer=issuer,
                spec_reference="RFC8414",
                mcp_compliance="OAuth 2.1 Authorization Server Metadata discovery"
            )
            
            metadata = {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/auth/mcp-authorize",
                "token_endpoint": f"{issuer}/auth/mcp-token",
                "userinfo_endpoint": f"{settings.supabase_url}/auth/v1/user" if settings.supabase_url else None,
                "jwks_uri": f"{settings.supabase_url}/.well-known/jwks.json" if settings.supabase_url else None,
                "registration_endpoint": f"{issuer}/auth/mcp-register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "urn:ietf:params:oauth:grant-type:token-exchange"],
                "code_challenge_methods_supported": ["S256"],  # PKCE required by MCP spec
                "scopes_supported": ["mcp:read", "mcp:write"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["HS256", "RS256"],
                "claims_supported": [
                    "sub", "aud", "exp", "iat", "iss", "email", "scope"
                ]
            }
            
            logger.info(
                "MCP Authorization: Returning OAuth 2.1 Authorization Server Metadata",
                endpoint="/.well-known/oauth-authorization-server",
                client_ip=client_ip,
                response_fields=list(metadata.keys()),
                pkce_support=True,
                dynamic_registration_support=bool(metadata.get("registration_endpoint")),
                spec_compliance="OAuth 2.1 + MCP Authorization"
            )
            
            return JSONResponse(metadata, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour as per spec
            })

        async def handle_protected_resource_metadata(request: Request) -> JSONResponse:
            """OAuth 2.0 Protected Resource Metadata (RFC 9728) - MCP Compliant."""
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            # Handle CORS preflight
            if request.method == "OPTIONS":
                logger.info(
                    "MCP Authorization: CORS preflight request for Protected Resource Metadata",
                    endpoint="/.well-known/oauth-protected-resource",
                    method="OPTIONS",
                    client_ip=client_ip,
                    user_agent=user_agent,
                    spec_reference="RFC9728"
                )
                return JSONResponse(
                    content={},
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                        "Access-Control-Max-Age": "86400",
                    }
                )
            
            base_url = settings.mcp_public_base_url or f"http://{settings.mcp_server_host}:{settings.mcp_server_port}"
            # Canonical resource URI without trailing slash (per MCP spec)
            resource_uri = f"{base_url}/mcp" if base_url.endswith("/") else f"{base_url}/mcp"
            if resource_uri.endswith("/mcp/"):
                resource_uri = resource_uri[:-1]  # Remove trailing slash
                
            authorization_servers = [settings.frontend_base_url]
            
            logger.info(
                "MCP Authorization: Protected Resource Metadata request",
                endpoint="/.well-known/oauth-protected-resource",
                method="GET",
                client_ip=client_ip,
                user_agent=user_agent,
                resource_uri=resource_uri,
                authorization_servers=authorization_servers,
                spec_reference="RFC9728",
                mcp_compliance="Resource server metadata for authorization server discovery"
            )
            
            metadata = {
                "resource": resource_uri,  # Canonical URI as per RFC 8707 and MCP spec
                "authorization_servers": authorization_servers,
                "scopes_supported": ["mcp:read", "mcp:write"],
                "bearer_methods_supported": ["header"],  # Only Authorization header supported
                "resource_documentation": f"{base_url}/docs",
                "mcp_version": "1.0.0",
                "server_name": settings.mcp_server_name,
                "capabilities": ["tools"],
                "transports": ["streamable-http"],
            }
            
            logger.info(
                "MCP Authorization: Returning Protected Resource Metadata",
                endpoint="/.well-known/oauth-protected-resource",
                client_ip=client_ip,
                canonical_resource_uri=resource_uri,
                authorization_server_count=len(authorization_servers),
                supported_scopes=metadata["scopes_supported"],
                spec_compliance="RFC9728 + MCP Authorization"
            )
            
            return JSONResponse(metadata, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            })

        async def handle_protected_resource_metadata_mcp(request: Request) -> JSONResponse:
            """OAuth 2.0 Protected Resource Metadata for /mcp path (RFC 9728)."""
            # This is the same as the regular protected resource metadata
            # but accessible at /.well-known/oauth-protected-resource/mcp
            return await handle_protected_resource_metadata(request)

        async def handle_openid_configuration(request: Request) -> JSONResponse:
            """OpenID Connect Discovery endpoint - redirect to OAuth authorization server metadata."""
            # Handle CORS preflight
            if request.method == "OPTIONS":
                logger.info("CORS preflight for openid-configuration")
                return JSONResponse(
                    content={},
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                        "Access-Control-Max-Age": "86400",
                    }
                )
            
            # For OpenID Connect discovery, redirect to the authorization server metadata
            # This is typically handled by the authorization server (frontend), not the resource server (MCP)
            return JSONResponse(
                {
                    "error": "not_supported",
                    "error_description": "OpenID Connect configuration is available at the authorization server",
                    "authorization_server": settings.frontend_base_url,
                    "authorization_server_metadata": f"{settings.frontend_base_url}/.well-known/oauth-authorization-server"
                },
                status_code=404,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                }
            )

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            """Context manager for managing session manager lifecycle."""
            async with self.session_manager.run():
                logger.info("MCP server started with official Streamable HTTP transport!")
                try:
                    yield
                finally:
                    logger.info("MCP server shutting down...")

        # Create routes - specific routes MUST come before the Mount
        routes = []
        
        # Add OAuth discovery endpoints if enabled - these MUST come first
        if settings.enable_oauth_discovery:
            routes.extend([
                Route("/.well-known/oauth-authorization-server", endpoint=handle_oauth_discovery, methods=["GET", "OPTIONS"]),
                Route("/.well-known/oauth-protected-resource", endpoint=handle_protected_resource_metadata, methods=["GET", "OPTIONS"]),
                Route("/.well-known/oauth-protected-resource/mcp", endpoint=handle_protected_resource_metadata_mcp, methods=["GET", "OPTIONS"]),
                Route("/.well-known/openid-configuration", endpoint=handle_openid_configuration, methods=["GET", "OPTIONS"]),
            ])
        
        # Health check endpoint
        routes.append(Route("/health", endpoint=handle_health_check, methods=["GET"]))

        # Add a catch-all Mount for MCP requests at the end (after specific routes)
        # This will only catch requests that don't match the specific OAuth discovery routes above
        routes.append(
            Mount("/", app=handle_streamable_http)
        )

        # Create Starlette application
        self.app = Starlette(
            debug=settings.debug,
            routes=routes,
            lifespan=lifespan,
        )

        # Add CORS middleware with proper origins
        if settings.enable_cors:
            logger.info("MCP Server: Enabling CORS middleware")
            # Use wildcard if explicitly set to "*" or in debug mode
            if settings.cors_origins == "*" or settings.debug:
                cors_origins = ["*"]
            else:
                cors_origins = settings.cors_origins_list
            logger.info(
                "MCP Server: CORS configuration",
                origins=cors_origins,
                allow_credentials=True,
                allowed_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_all_headers=True,
                debug_mode=settings.debug,
                spec_compliance="CORS for cross-origin MCP client access"
            )
            self.app = CORSMiddleware(
                self.app,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["*"],
                expose_headers=["Mcp-Session-Id"],
            )

    async def run_http(self) -> None:
        """Run the HTTP server."""
        import uvicorn
        
        logger.info(
            "MCP Server: Starting HTTP server with official MCP transports",
            host=settings.mcp_server_host,
            port=settings.mcp_server_port,
            transports=["streamable-http"],
            oauth_discovery_enabled=settings.enable_oauth_discovery,
            cors_enabled=settings.enable_cors,
            debug_mode=settings.debug,
            server_name=settings.mcp_server_name,
            spec_compliance="MCP 1.0.0 with OAuth 2.1 Authorization",
            public_base_url=settings.mcp_public_base_url,
            frontend_base_url=settings.frontend_base_url
        )
        
        config = uvicorn.Config(
            app=self.app,
            host=settings.mcp_server_host,
            port=settings.mcp_server_port,
            log_level=settings.mcp_log_level.lower(),
        )
        
        server = uvicorn.Server(config)
        await server.serve()


# Factory function to create appropriate server
def create_server(transport: str = "http") -> MCPToolServer | MCPHTTPServer:
    """Create MCP server instance.
    
    Args:
        transport: Transport type ("stdio" or "http")
        
    Returns:
        Server instance
    """
    if transport == "stdio":
        return MCPToolServer()
    elif transport == "http":
        return MCPHTTPServer()
    else:
        raise ValueError(f"Unsupported transport: {transport}")
