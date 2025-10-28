"""Local Docker-based sandbox for NHS Analytics development.

Provides E2B-compatible interface for running code in local Docker containers.
Used for local development where the database is accessible via Docker networking.

This implementation maintains persistent Python session state between executions,
similar to E2B's AsyncSandbox behavior.
"""

import asyncio
import base64
import io
import json
import secrets
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import docker
from docker.models.containers import Container
from docker.errors import DockerException, ImageNotFound, NotFound

from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

logger = get_logger(__name__)


@dataclass
class ExecutionLogs:
    """Container for execution logs."""
    stdout: List[str] = field(default_factory=list)
    stderr: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of code execution in Docker sandbox."""
    error: Optional[Exception] = None
    logs: Optional[ExecutionLogs] = None
    results: List[Dict[str, Any]] = field(default_factory=list)


class DockerLocalSandbox:
    """Local Docker-based sandbox that mimics E2B AsyncSandbox interface.

    This sandbox runs Python code in temporary Docker containers on the same
    Docker network as the MCP server, allowing access to the local database.

    Features persistent Python session state between executions within the same
    sandbox instance, making it compatible with E2B's AsyncSandbox behavior.

    Designed to be a drop-in replacement for E2B's AsyncSandbox during local
    development.
    """

    # State persistence file path in container
    STATE_FILE = "/tmp/sandbox_state.pkl"
    WORKSPACE_DIR = "/workspace"

    def __init__(
        self,
        container: Container,
        sandbox_id: str,
        docker_client: docker.DockerClient,
        network_name: str,
        timeout: int = 600
    ):
        """Initialize Docker sandbox.

        Args:
            container: Docker container instance
            sandbox_id: Unique identifier for this sandbox
            docker_client: Docker client instance
            network_name: Docker network name to connect to
            timeout: Default timeout in seconds
        """
        self.container = container
        self.sandbox_id = sandbox_id
        self._docker_client = docker_client
        self._network_name = network_name
        self._timeout = timeout
        self._is_killed = False
        self._execution_count = 0

    @classmethod
    async def create(
        cls,
        timeout: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
        network_name: str = "e18-agent-os_default",
        **kwargs
    ) -> "DockerLocalSandbox":
        """Create a new Docker sandbox.

        Args:
            timeout: Timeout in seconds (default: 600)
            metadata: Metadata for the sandbox (for compatibility with E2B)
            network_name: Docker network to attach to
            **kwargs: Additional arguments (ignored, for E2B compatibility)

        Returns:
            DockerLocalSandbox instance

        Raises:
            ToolExecutionError: If Docker is not available or container creation fails
        """
        timeout = timeout or 600
        sandbox_id = f"nhs-sandbox-{secrets.token_hex(8)}"

        logger.info(
            "Creating local Docker sandbox with persistent session",
            sandbox_id=sandbox_id,
            network=network_name,
            timeout=timeout
        )

        try:
            # Initialize Docker client
            docker_client = docker.from_env()

            # Test Docker connectivity
            docker_client.ping()

            # Ensure python:3.12-slim image is available (pull if needed)
            try:
                docker_client.images.get("python:3.12-slim")
                logger.debug("python:3.12-slim image already available")
            except ImageNotFound:
                logger.info(
                    "python:3.12-slim not found locally, pulling image",
                    note="This may take a few minutes on first run"
                )
                try:
                    docker_client.images.pull("python:3.12-slim")
                    logger.info("Successfully pulled python:3.12-slim image")
                except DockerException as pull_error:
                    raise ToolExecutionError(
                        "docker_sandbox",
                        f"Failed to pull python:3.12-slim image: {str(pull_error)}"
                    )

            # Create container with Python
            container = docker_client.containers.create(
                image="python:3.12-slim",
                name=sandbox_id,
                command="sleep infinity",  # Keep container running
                detach=True,
                network=network_name,
                labels={
                    "nhs-analytics-sandbox": "true",
                    "sandbox-id": sandbox_id,
                    **(metadata or {})
                },
                # Resource limits
                mem_limit="2g",
                cpu_quota=100000,  # 1 CPU
            )

            # Start the container
            container.start()

            # Wait for container to be running
            await asyncio.sleep(0.5)
            container.reload()

            if container.status != "running":
                raise ToolExecutionError(
                    "docker_sandbox",
                    f"Container failed to start: {container.status}"
                )

            # Create workspace directory
            exit_code, _ = container.exec_run(["mkdir", "-p", cls.WORKSPACE_DIR])
            if exit_code != 0:
                logger.warning("Failed to create workspace directory")

            logger.info(
                "Docker sandbox created successfully with persistent session support",
                sandbox_id=sandbox_id,
                container_id=container.id[:12]
            )

            return cls(container, sandbox_id, docker_client, network_name, timeout)

        except DockerException as e:
            logger.error(f"Failed to create Docker sandbox: {e}", exc_info=True)
            raise ToolExecutionError(
                "docker_sandbox",
                f"Docker error: {str(e)}. Is Docker running?"
            )
        except Exception as e:
            logger.error(f"Unexpected error creating sandbox: {e}", exc_info=True)
            raise ToolExecutionError(
                "docker_sandbox",
                f"Failed to create sandbox: {str(e)}"
            )

    def _wrap_code_with_persistence(self, user_code: str) -> str:
        """Wrap user code with state persistence logic.

        This enables persistent Python sessions by:
        1. Loading previous session state (variables, imports)
        2. Executing user code
        3. Saving session state for next execution

        Args:
            user_code: The user's Python code to execute

        Returns:
            Wrapped code with state persistence
        """
        wrapper = f'''
import sys
import os
import pickle
import traceback
from io import StringIO

STATE_FILE = "{self.STATE_FILE}"

# Redirect stdout/stderr to capture output
_original_stdout = sys.stdout
_original_stderr = sys.stderr
_captured_stdout = StringIO()
_captured_stderr = StringIO()
sys.stdout = _captured_stdout
sys.stderr = _captured_stderr

try:
    # Load previous session state if it exists
    _session_globals = {{}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'rb') as _f:
                _session_globals = pickle.load(_f)
            print("[Session] Restored state from previous execution", file=_original_stdout)
        except Exception as _e:
            print(f"[Session] Warning: Could not restore state: {{_e}}", file=_original_stderr)
    else:
        print("[Session] Starting fresh session", file=_original_stdout)

    # Update globals with restored state
    globals().update(_session_globals)

    # Execute user code
    exec("""\\
{user_code}
""", globals())

    # Save session state (excluding private/module variables)
    _state_to_save = {{
        k: v for k, v in globals().items()
        if not k.startswith('_')
        and k not in ['sys', 'os', 'pickle', 'traceback', 'StringIO', 'STATE_FILE']
        and not callable(v) or k in ['pd', 'np', 'plt', 'sns']  # Keep common aliases even if callable
    }}

    try:
        with open(STATE_FILE, 'wb') as _f:
            pickle.dump(_state_to_save, _f)
        print(f"[Session] Saved {{len(_state_to_save)}} variables to state", file=_original_stdout)
    except Exception as _e:
        print(f"[Session] Warning: Could not save state: {{_e}}", file=_original_stderr)

except Exception as _error:
    # Capture exception details
    _error_details = traceback.format_exc()
    print(_error_details, file=_captured_stderr)

finally:
    # Restore stdout/stderr
    sys.stdout = _original_stdout
    sys.stderr = _original_stderr

    # Print captured output
    _stdout_content = _captured_stdout.getvalue()
    _stderr_content = _captured_stderr.getvalue()

    if _stdout_content:
        print(_stdout_content, end='')
    if _stderr_content:
        print(_stderr_content, end='', file=sys.stderr)
'''
        return wrapper

    async def run_code(
        self,
        code: str,
        envs: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> ExecutionResult:
        """Execute Python code in the sandbox with persistent session state.

        This method maintains state between executions within the same sandbox
        instance, similar to E2B's AsyncSandbox behavior. Variables, imports,
        and other state persist across multiple run_code calls.

        Args:
            code: Python code to execute
            envs: Environment variables to set
            timeout: Execution timeout in seconds
            **kwargs: Additional arguments (ignored, for E2B compatibility)

        Returns:
            ExecutionResult with stdout, stderr, and error if any
        """
        if self._is_killed:
            raise ToolExecutionError("docker_sandbox", "Sandbox has been killed")

        timeout = timeout or self._timeout
        envs = envs or {}
        self._execution_count += 1

        logger.info(
            "Executing code in Docker sandbox with persistent session",
            sandbox_id=self.sandbox_id,
            execution_count=self._execution_count,
            code_length=len(code),
            timeout=timeout
        )

        try:
            # Refresh container state
            self.container.reload()

            if self.container.status != "running":
                raise ToolExecutionError(
                    "docker_sandbox",
                    f"Container is not running: {self.container.status}"
                )

            # Wrap code with persistence logic
            wrapped_code = self._wrap_code_with_persistence(code)

            # Encode code to avoid shell escaping issues
            code_b64 = base64.b64encode(wrapped_code.encode()).decode()

            # Execute command using list format to avoid quote escaping issues
            exit_code, output = self.container.exec_run(
                ["python3", "-c", f"import base64; exec(base64.b64decode('{code_b64}').decode())"],
                demux=True,  # Separate stdout and stderr
                stream=False,
                environment=envs
            )

            # Process output
            stdout_bytes, stderr_bytes = output

            stdout_lines = []
            if stdout_bytes:
                stdout_text = stdout_bytes.decode('utf-8', errors='replace')
                stdout_lines = stdout_text.strip().split('\n') if stdout_text.strip() else []

            stderr_lines = []
            if stderr_bytes:
                stderr_text = stderr_bytes.decode('utf-8', errors='replace')
                stderr_lines = stderr_text.strip().split('\n') if stderr_text.strip() else []

            logs = ExecutionLogs(stdout=stdout_lines, stderr=stderr_lines)

            # Check for errors
            error = None
            if exit_code != 0:
                error_msg = '\n'.join(stderr_lines) if stderr_lines else f"Exit code: {exit_code}"
                error = Exception(f"ExecutionError: {error_msg}")

            result = ExecutionResult(
                error=error,
                logs=logs,
                results=[]  # TODO: Parse JSON results from stdout if needed
            )

            logger.info(
                "Code execution completed",
                sandbox_id=self.sandbox_id,
                execution_count=self._execution_count,
                exit_code=exit_code,
                stdout_lines=len(stdout_lines),
                stderr_lines=len(stderr_lines),
                has_error=error is not None
            )

            return result

        except Exception as e:
            logger.error(f"Error executing code in sandbox: {e}", exc_info=True)
            return ExecutionResult(
                error=Exception(f"Execution failed: {str(e)}"),
                logs=ExecutionLogs(stdout=[], stderr=[str(e)]),
                results=[]
            )

    async def is_running(self) -> bool:
        """Check if the sandbox container is still running.

        Returns:
            True if container is running, False otherwise
        """
        if self._is_killed:
            return False

        try:
            self.container.reload()
            return self.container.status == "running"
        except NotFound:
            return False
        except Exception as e:
            logger.warning(f"Error checking sandbox status: {e}")
            return False

    async def set_timeout(self, timeout: int) -> None:
        """Update the sandbox timeout.

        Args:
            timeout: New timeout in seconds
        """
        self._timeout = timeout
        logger.debug(f"Updated sandbox timeout to {timeout}s", sandbox_id=self.sandbox_id)

    async def kill(self) -> None:
        """Stop and remove the sandbox container.

        This method is idempotent and safe to call multiple times.
        """
        if self._is_killed:
            return

        logger.info(
            "Killing Docker sandbox",
            sandbox_id=self.sandbox_id,
            total_executions=self._execution_count
        )

        try:
            self.container.stop(timeout=5)
            self.container.remove(force=True)
            self._is_killed = True
            logger.info("Docker sandbox killed successfully", sandbox_id=self.sandbox_id)
        except NotFound:
            # Container already removed
            self._is_killed = True
            logger.debug("Container already removed", sandbox_id=self.sandbox_id)
        except Exception as e:
            logger.error(f"Error killing sandbox: {e}", exc_info=True)
            # Try force removal
            try:
                self.container.remove(force=True)
                self._is_killed = True
            except Exception:
                pass

    def __del__(self):
        """Cleanup on garbage collection."""
        if not self._is_killed:
            try:
                # Synchronous cleanup
                self.container.stop(timeout=2)
                self.container.remove(force=True)
            except Exception:
                pass
