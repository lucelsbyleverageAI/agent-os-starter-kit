"""E2B Code Sandbox execution tool."""

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from e2b_code_interpreter import AsyncSandbox

from ...config import settings
from ...utils.exceptions import ToolExecutionError
from ...utils.logging import get_logger
from ..base import CustomTool, ToolParameter

# Supabase storage utilities for output handling
try:
    from ...utils.supabase_storage import (
        OutputMetadata,
        generate_output_filename,
        upload_output_to_supabase,
        is_supabase_storage_available,
    )
    SUPABASE_STORAGE_AVAILABLE = is_supabase_storage_available()
except ImportError:
    SUPABASE_STORAGE_AVAILABLE = False

logger = get_logger(__name__)


class E2BExecuteCodeTool(CustomTool):
    """Execute Python code in a persistent E2B sandbox environment."""
    
    # Toolkit configuration
    toolkit_name = "e2b_code_sandbox"
    toolkit_display_name = "E2B Code Sandbox"
    
    # Hardcoded configuration values
    DEFAULT_TIMEOUT = 300  # 5 minutes
    REQUEST_TIMEOUT = 60   # 1 minute for API requests
    MAX_STDOUT_LINES = 1000
    MAX_STDERR_LINES = 1000
    MAX_STRING_LENGTH = 50000
    
    def __init__(self) -> None:
        super().__init__()
        self._sandbox_cache: Dict[Tuple[str, str], AsyncSandbox] = {}
        
    @property
    def name(self) -> str:
        """Tool name."""
        return "execute_code"
    
    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Execute Python code in a persistent, isolated E2B sandbox with rich data science libraries pre-installed. "
            "The sandbox includes pandas, numpy, matplotlib, seaborn, plotly, scikit-learn, opencv, and many more. "
            "Maintains stateful execution - variables, imports, and functions persist between calls using thread_id. "
            "Automatically captures print() outputs, matplotlib plots (as images), and rich display results (HTML, JSON, etc.). "
            "Perfect for data analysis, visualization, and multi-step workflows. "
            "Use thread_id to maintain state across multiple code executions in the same conversation."
        )
    
    def get_parameters(self) -> List[ToolParameter]:
        """Get tool parameters."""
        return [
            ToolParameter(
                name="code",
                type="string",
                description=(
                    "Python code to execute in the sandbox. Use print() for text output, "
                    "matplotlib/seaborn/plotly for plots (automatically captured as images), "
                    "and display() for rich outputs. Variables persist between executions."
                ),
                required=True,
            ),
            ToolParameter(
                name="thread_id",
                type="string", 
                description="Thread/conversation identifier for sandbox persistence. If omitted, uses a default per-user sandbox.",
                required=False,
            ),
            ToolParameter(
                name="sandbox_id",
                type="string",
                description="Connect to this specific sandbox ID instead of thread-based lookup",
                required=False,
            ),
            ToolParameter(
                name="reset",
                type="boolean",
                description="Kill any existing sandbox for this user/thread before execution",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="pip_packages",
                type="array",
                description="Python packages to install via pip before execution",
                required=False,
                items={"type": "string"},
            ),
            ToolParameter(
                name="timeout_seconds",
                type="integer", 
                description="Override execution timeout in seconds (max 600)",
                required=False,
            ),
            ToolParameter(
                name="close_sandbox",
                type="boolean",
                description="Kill the sandbox after execution (cleanup)",
                required=False,
                default=False,
            ),
        ]
    
    async def _execute_impl(self, user_id: str, **kwargs: Any) -> Any:
        """Execute the E2B code sandbox tool."""
        # Validate E2B API key is configured
        if not settings.e2b_api_key:
            raise ToolExecutionError(
                "e2b_code_sandbox",
                "E2B API key not configured. Please set E2B_API_KEY environment variable."
            )

        # Extract parameters
        code = kwargs.get("code", "").strip()
        thread_id = kwargs.get("thread_id") or kwargs.get("_context_thread_id") or "default"
        sandbox_id = kwargs.get("sandbox_id")
        reset = kwargs.get("reset", False)
        pip_packages = kwargs.get("pip_packages", [])
        timeout_seconds = min(kwargs.get("timeout_seconds", self.DEFAULT_TIMEOUT), 600)
        close_sandbox = kwargs.get("close_sandbox", False)

        # Extract context for storage (assistant_id from LangGraph context injection)
        assistant_id = kwargs.get("_context_assistant_id") or "unknown"
        
        if not code:
            raise ToolExecutionError("e2b_code_sandbox", "No code provided to execute")
        
        logger.info(
            "E2B code execution started", 
            user_id=user_id,
            thread_id=thread_id,
            sandbox_id=sandbox_id,
            reset=reset,
            code_length=len(code),
            pip_packages=pip_packages,
        )
        
        sandbox = None
        execution_sandbox_id = None
        
        try:
            # Get or create sandbox
            sandbox, execution_sandbox_id = await self._get_or_create_sandbox(
                user_id, thread_id, sandbox_id, reset
            )
            
            # Install pip packages if specified
            if pip_packages:
                await self._install_packages(sandbox, pip_packages)
            
            # Execute the code
            execution = await sandbox.run_code(
                code,
                timeout=timeout_seconds,
                request_timeout=self.REQUEST_TIMEOUT,
            )
            
            # Process results
            result = await self._process_execution_result(
                execution, user_id, assistant_id, thread_id, execution_sandbox_id
            )
            
            # Handle sandbox cleanup
            if close_sandbox:
                await self._cleanup_sandbox(user_id, thread_id, execution_sandbox_id)
            
            logger.info(
                "E2B code execution completed",
                user_id=user_id,
                sandbox_id=execution_sandbox_id,
                success=result["success"],
            )
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(
                "E2B code execution failed",
                user_id=user_id,
                sandbox_id=execution_sandbox_id,
                error=str(e),
            )
            
            # Clean up on error if requested
            if close_sandbox and execution_sandbox_id:
                await self._cleanup_sandbox(user_id, thread_id, execution_sandbox_id)
            
            # Return error result
            return json.dumps({
                "success": False,
                "error": str(e),
                "sandbox_id": execution_sandbox_id,
                "thread_id": thread_id,
                "stdout": [],
                "stderr": [],
                "text": None,
                "results": [],
            }, indent=2)
    
    async def _get_or_create_sandbox(
        self, 
        user_id: str, 
        thread_id: str, 
        sandbox_id: Optional[str],
        reset: bool
    ) -> Tuple[AsyncSandbox, str]:
        """Get or create a sandbox for the user/thread."""
        cache_key = (user_id, thread_id)
        
        # Handle reset request
        if reset:
            await self._cleanup_sandbox(user_id, thread_id, None)
        
        # Handle specific sandbox ID
        if sandbox_id:
            try:
                sandbox = await AsyncSandbox.connect(sandbox_id, api_key=settings.e2b_api_key)
                # Update timeout
                await sandbox.set_timeout(self.DEFAULT_TIMEOUT)
                logger.info("Connected to specific sandbox", sandbox_id=sandbox_id)
                return sandbox, sandbox_id
            except Exception as e:
                logger.warning(
                    "Failed to connect to specific sandbox, creating new one",
                    sandbox_id=sandbox_id,
                    error=str(e),
                )
        
        # Check cache first
        if cache_key in self._sandbox_cache and not reset:
            try:
                sandbox = self._sandbox_cache[cache_key]
                # Verify sandbox is alive by checking if it's running
                is_running = await sandbox.is_running()
                if not is_running:
                    # Remove dead sandbox from cache
                    del self._sandbox_cache[cache_key]
                    logger.debug("Removed dead sandbox from cache")
                else:
                    # Update timeout
                    await sandbox.set_timeout(self.DEFAULT_TIMEOUT)
                    logger.info("Using cached sandbox", sandbox_id=sandbox.sandbox_id)
                    return sandbox, sandbox.sandbox_id
            except Exception:
                # Remove dead sandbox from cache
                del self._sandbox_cache[cache_key]
                logger.debug("Removed dead sandbox from cache")
        
        # Try to find existing sandbox via metadata
        if not reset:
            try:
                existing_sandbox_id = await self._find_existing_sandbox(user_id, thread_id)
                if existing_sandbox_id:
                    sandbox = await AsyncSandbox.connect(existing_sandbox_id, api_key=settings.e2b_api_key)
                    await sandbox.set_timeout(self.DEFAULT_TIMEOUT)
                    self._sandbox_cache[cache_key] = sandbox
                    logger.info("Reconnected to existing sandbox", sandbox_id=existing_sandbox_id)
                    return sandbox, existing_sandbox_id
            except Exception as e:
                logger.warning(
                    "Failed to reconnect to existing sandbox",
                    user_id=user_id,
                    thread_id=thread_id,
                    error=str(e),
                )
        
        # Create new sandbox
        metadata = {
            "user_id": user_id,
            "thread_id": thread_id,
            "purpose": "e2b_code_sandbox_mcp",
            "created_at": str(int(time.time())),
        }
        
        sandbox = await AsyncSandbox.create(
            timeout=self.DEFAULT_TIMEOUT,
            metadata=metadata,
            api_key=settings.e2b_api_key,
            request_timeout=self.REQUEST_TIMEOUT,
        )
        
        # Cache the new sandbox
        self._sandbox_cache[cache_key] = sandbox
        
        logger.info("Created new sandbox", sandbox_id=sandbox.sandbox_id, metadata=metadata)
        
        return sandbox, sandbox.sandbox_id
    
    async def _find_existing_sandbox(self, user_id: str, thread_id: str) -> Optional[str]:
        """Find existing sandbox by metadata - simplified approach without listing API."""
        # For now, we'll rely on the in-memory cache since the E2B API doesn't 
        # provide a simple way to list sandboxes by metadata
        # This means sandboxes will be created fresh when the server restarts
        # but will persist within a server session
        logger.debug(
            "Skipping sandbox search - relying on cache and creating new if needed",
            user_id=user_id,
            thread_id=thread_id,
        )
        return None
    
    async def _install_packages(self, sandbox: AsyncSandbox, packages: List[str]) -> None:
        """Install Python packages in the sandbox."""
        if not packages:
            return
        
        # Build pip install command
        packages_str = " ".join(f'"{pkg}"' for pkg in packages)
        install_code = f"""
import subprocess
import sys

print("Installing packages: {packages_str}")
try:
    result = subprocess.run([
        sys.executable, "-m", "pip", "install", "--quiet"
    ] + {packages!r}, capture_output=True, text=True, timeout=120)
    
    if result.returncode == 0:
        print("✅ Packages installed successfully")
    else:
        print(f"❌ Package installation failed: {{result.stderr}}")
        
except Exception as e:
    print(f"❌ Package installation error: {{e}}")
"""
        
        try:
            execution = await sandbox.run_code(
                install_code, 
                timeout=180,  # 3 minutes for package installation
                request_timeout=self.REQUEST_TIMEOUT,
            )
            
            if execution.error:
                logger.warning(
                    "Package installation had errors", 
                    packages=packages,
                    error=str(execution.error),
                )
            else:
                logger.info("Packages installed successfully", packages=packages)
                
        except Exception as e:
            logger.error("Failed to install packages", packages=packages, error=str(e))
            # Don't fail the entire execution for package installation errors
    
    async def _process_execution_result(
        self,
        execution: Any,
        user_id: str,
        assistant_id: str,
        thread_id: str,
        sandbox_id: str
    ) -> Dict[str, Any]:
        """Process E2B execution result into structured format."""
        # Base result structure
        result = {
            "success": not bool(execution.error),
            "sandbox_id": sandbox_id,
            "text": execution.text,
            "error": str(execution.error) if execution.error else None,
            "stdout": [],
            "stderr": [],
            "results": [],
            "rich_outputs": [],
        }
        
        # Process logs
        if execution.logs:
            if execution.logs.stdout:
                result["stdout"] = self._truncate_logs(execution.logs.stdout, self.MAX_STDOUT_LINES)
            if execution.logs.stderr:
                result["stderr"] = self._truncate_logs(execution.logs.stderr, self.MAX_STDERR_LINES)
        
        # Process rich results
        if execution.results:
            for res in execution.results:
                result_data = {
                    "type": str(type(res).__name__),
                    "text": getattr(res, "text", None),
                    "is_main_result": getattr(res, "is_main_result", False),
                }
                
                # Handle image outputs
                if hasattr(res, "png") and res.png:
                    image_info = await self._process_image(
                        res.png, "image/png", "png", user_id, assistant_id, thread_id
                    )
                    result["rich_outputs"].append(image_info)
                    result_data["has_png"] = True
                    if image_info.get("storage_url"):
                        result_data["png_storage_url"] = image_info["storage_url"]

                if hasattr(res, "svg") and res.svg:
                    image_info = await self._process_image(
                        res.svg, "image/svg+xml", "svg", user_id, assistant_id, thread_id
                    )
                    result["rich_outputs"].append(image_info)
                    result_data["has_svg"] = True
                    if image_info.get("storage_url"):
                        result_data["svg_storage_url"] = image_info["storage_url"]
                
                # Handle other outputs
                for attr in ["html", "json", "javascript", "latex"]:
                    if hasattr(res, attr):
                        value = getattr(res, attr)
                        if value:
                            result_data[attr] = self._truncate_string(value)
                
                result["results"].append(result_data)
        
        return result
    
    async def _process_image(
        self,
        image_data: str,
        content_type: str,
        format: str,
        user_id: str,
        assistant_id: str,
        thread_id: str
    ) -> Dict[str, Any]:
        """Process image data for storage or base64 return."""
        # Always attempt to upload to Supabase storage
        if SUPABASE_STORAGE_AVAILABLE:
            try:
                # Convert image data to bytes
                if content_type == "image/svg+xml":
                    output_bytes = image_data.encode('utf-8')
                else:
                    import base64
                    output_bytes = base64.b64decode(image_data)

                # Generate filename with proper path structure
                filename = generate_output_filename(
                    user_id=user_id,
                    assistant_id=assistant_id,
                    thread_id=thread_id,
                    tool_name="e2b_code_sandbox",
                    format=format
                )

                # Create metadata
                metadata = OutputMetadata(
                    filename=filename,
                    user_id=user_id,
                    assistant_id=assistant_id,
                    thread_id=thread_id,
                    tool_name="e2b_code_sandbox",
                    content_type=content_type,
                    size_bytes=len(output_bytes),
                    format=format,
                    additional_metadata={
                        "source": "e2b_sandbox_execution",
                    }
                )

                # Upload to Supabase Storage
                _, storage_url = upload_output_to_supabase(
                    output_bytes, metadata, content_type
                )

                return {
                    "type": content_type,
                    "storage_url": storage_url,
                    "filename": filename,
                    "format": "storage_url",
                    "size_bytes": len(output_bytes),
                }

            except Exception as e:
                logger.warning(
                    "Failed to upload output to Supabase Storage, falling back to base64",
                    error=str(e),
                    user_id=user_id,
                    assistant_id=assistant_id,
                    thread_id=thread_id,
                )

        # Fallback to base64 (if Supabase unavailable or upload failed)
        return {
            "type": content_type,
            "data": image_data,
            "format": "base64" if content_type != "image/svg+xml" else "text",
        }
    
    def _truncate_logs(self, logs: List[str], max_lines: int) -> List[str]:
        """Truncate log lines to prevent excessive output."""
        if len(logs) <= max_lines:
            return logs
        
        truncated = logs[:max_lines]
        truncated.append(f"... [TRUNCATED: {len(logs) - max_lines} more lines]")
        return truncated
    
    def _truncate_string(self, text: str) -> str:
        """Truncate string to prevent excessive output."""
        if len(text) <= self.MAX_STRING_LENGTH:
            return text
        
        return text[:self.MAX_STRING_LENGTH] + f"... [TRUNCATED: {len(text) - self.MAX_STRING_LENGTH} more characters]"
    
    async def _cleanup_sandbox(
        self, 
        user_id: str, 
        thread_id: str, 
        sandbox_id: Optional[str]
    ) -> None:
        """Clean up sandbox and remove from cache."""
        cache_key = (user_id, thread_id)
        
        # Remove from cache
        if cache_key in self._sandbox_cache:
            try:
                sandbox = self._sandbox_cache[cache_key]
                await sandbox.kill()
                logger.info("Killed cached sandbox", sandbox_id=sandbox_id)
            except Exception as e:
                logger.warning("Failed to kill cached sandbox", error=str(e))
            finally:
                del self._sandbox_cache[cache_key]
        
        # Kill specific sandbox if provided
        if sandbox_id and sandbox_id != "unknown":
            try:
                # Use static method to kill by ID
                killed = await AsyncSandbox.kill(sandbox_id, api_key=settings.e2b_api_key)
                if killed:
                    logger.info("Killed specific sandbox", sandbox_id=sandbox_id)
                else:
                    logger.warning("Sandbox not found when trying to kill", sandbox_id=sandbox_id)
            except Exception as e:
                logger.warning("Failed to kill specific sandbox", sandbox_id=sandbox_id, error=str(e))
