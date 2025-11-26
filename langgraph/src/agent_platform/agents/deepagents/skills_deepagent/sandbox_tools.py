"""
E2B Sandbox tools for Skills DeepAgent.

This module provides two tools for interacting with the E2B sandbox environment:

1. `run_code` - Jupyter-style code interpreter for Python/bash/JavaScript
   - Best for: Writing files, data processing, complex multi-line operations
   - Uses E2B's code interpreter which handles multi-line content naturally

2. `run_command` - Direct shell command execution
   - Best for: Quick operations (ls, cat, head), running existing scripts, pip install
   - Uses E2B's commands.run() for simple shell commands

Design Decision:
We provide two tools because:
1. Code interpreter handles multi-line content, file writing, and complex logic naturally
2. Shell commands are better for quick operations and running existing scripts
3. Both share the same filesystem and environment (pip installs are visible to both)
4. This avoids bash escaping issues (heredocs, quotes) that break with commands.run()
"""

import io
import logging
import os
import zipfile
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from langchain_core.tools import tool

log = logging.getLogger(__name__)


# Global sandbox instances keyed by thread_id
_sandboxes: Dict[str, Any] = {}


async def fetch_skill_zip(
    skill_id: str,
    langconnect_url: str,
    access_token: str
) -> Optional[bytes]:
    """
    Fetch skill zip file from LangConnect.

    Args:
        skill_id: UUID of the skill
        langconnect_url: Base URL of LangConnect API
        access_token: Supabase access token

    Returns:
        Bytes of the skill zip file or None if fetch failed
    """
    try:
        async with httpx.AsyncClient() as client:
            # Get signed download URL from LangConnect
            download_endpoint = f"{langconnect_url}/skills/{skill_id}/download"
            log.info(f"[skills:fetch] Requesting download URL from: {download_endpoint}")

            response = await client.get(
                download_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )
            response.raise_for_status()
            download_info = response.json()
            download_url = download_info.get("download_url")

            if not download_url:
                log.error(f"No download URL returned for skill {skill_id}")
                return None

            # Log the download URL to help debug DNS issues
            log.info(f"[skills:fetch] Got download URL for skill {skill_id}: {download_url[:100]}...")

            # Download the zip file from Supabase storage
            log.info(f"[skills:fetch] Downloading skill zip from signed URL...")
            zip_response = await client.get(download_url, timeout=60.0)
            zip_response.raise_for_status()
            log.info(f"[skills:fetch] Successfully downloaded skill {skill_id} ({len(zip_response.content)} bytes)")
            return zip_response.content

    except Exception as e:
        log.error(f"Failed to fetch skill {skill_id}: {e}")
        return None


def extract_and_upload_skill(sandbox: Any, skill_name: str, zip_content: bytes):
    """
    Extract skill zip and upload to sandbox.

    Args:
        sandbox: E2B Sandbox instance
        skill_name: Name of the skill (used for directory name)
        zip_content: Raw bytes of the skill zip file
    """
    try:
        skill_dir = f"/sandbox/skills/{skill_name}"
        sandbox.files.make_dir(skill_dir)

        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            for file_info in zf.infolist():
                if file_info.is_dir():
                    continue

                # Get file path relative to zip root
                file_path = file_info.filename
                # Remove any top-level directory if present
                parts = file_path.split('/')
                if len(parts) > 1 and parts[0] != 'SKILL.md':
                    # Skip the first directory level if it's a wrapper
                    file_path = '/'.join(parts[1:]) if parts[1:] else file_path

                if not file_path:
                    continue

                # Create full path in sandbox
                full_path = f"{skill_dir}/{file_path}"

                # Create parent directories
                parent_dir = '/'.join(full_path.split('/')[:-1])
                try:
                    sandbox.files.make_dir(parent_dir)
                except Exception:
                    pass  # Directory might already exist

                # Upload file content
                content = zf.read(file_info.filename)
                sandbox.files.write(full_path, content)

        log.info(f"Uploaded skill {skill_name} to {skill_dir}")

    except Exception as e:
        log.error(f"Failed to extract/upload skill {skill_name}: {e}")


async def get_or_create_sandbox(
    thread_id: str,
    skills: List[Dict[str, Any]],
    langconnect_url: str,
    access_token: str,
    pip_packages: Optional[List[str]] = None,
    timeout: int = 600
) -> Any:
    """
    Get existing sandbox or create new one with skills uploaded.

    Args:
        thread_id: Unique identifier for this thread/conversation
        skills: List of skill references with skill_id and name
        langconnect_url: Base URL of LangConnect API
        access_token: Supabase access token for skill downloads
        pip_packages: Additional pip packages to install
        timeout: Sandbox timeout in seconds

    Returns:
        E2B Sandbox instance
    """
    global _sandboxes

    if thread_id in _sandboxes:
        return _sandboxes[thread_id]

    # Import E2B here to avoid startup import issues
    try:
        from e2b_code_interpreter import Sandbox
    except ImportError:
        log.error("e2b_code_interpreter not installed. Install with: pip install e2b-code-interpreter")
        raise ImportError("e2b_code_interpreter package required for sandbox support")

    # Get E2B API key from environment
    e2b_api_key = os.environ.get("E2B_API_KEY")
    if not e2b_api_key:
        log.warning("E2B_API_KEY not set - sandbox features will be limited")

    # Create new sandbox
    sandbox = Sandbox(timeout=timeout, api_key=e2b_api_key)

    # Create directory structure
    sandbox.files.make_dir("/sandbox/skills")
    sandbox.files.make_dir("/sandbox/user_uploads")  # User uploaded files
    sandbox.files.make_dir("/sandbox/shared")
    sandbox.files.make_dir("/sandbox/shared/research")
    sandbox.files.make_dir("/sandbox/shared/drafts")
    sandbox.files.make_dir("/sandbox/outputs")
    sandbox.files.make_dir("/sandbox/workspace")

    # Upload skills
    all_pip_requirements = set(pip_packages or [])

    for skill in skills:
        skill_id = skill.get("skill_id")
        skill_name = skill.get("name")

        if not skill_id or not skill_name:
            continue

        # Fetch skill zip
        zip_content = await fetch_skill_zip(skill_id, langconnect_url, access_token)
        if zip_content:
            extract_and_upload_skill(sandbox, skill_name, zip_content)

            # Extract pip requirements from skill (if stored in skill reference)
            pip_reqs = skill.get("pip_requirements")
            if pip_reqs:
                all_pip_requirements.update(pip_reqs)

    # Install pip packages if specified
    if all_pip_requirements:
        packages_str = ' '.join(all_pip_requirements)
        log.info(f"Installing pip packages: {packages_str}")
        sandbox.commands.run(f"pip install {packages_str}")

    _sandboxes[thread_id] = sandbox
    log.info(f"Created sandbox for thread {thread_id} with {len(skills)} skills")

    return sandbox


def get_sandbox(thread_id: str) -> Optional[Any]:
    """
    Get existing sandbox for a thread.

    Args:
        thread_id: Thread identifier

    Returns:
        Sandbox instance or None if not found
    """
    return _sandboxes.get(thread_id)


def cleanup_sandbox(thread_id: str):
    """
    Clean up and remove sandbox for a thread.

    Args:
        thread_id: Thread identifier
    """
    global _sandboxes
    if thread_id in _sandboxes:
        try:
            _sandboxes[thread_id].close()
        except Exception as e:
            log.warning(f"Error closing sandbox for thread {thread_id}: {e}")
        del _sandboxes[thread_id]


def create_sandbox_tools(thread_id: str) -> Tuple[Any, Any]:
    """
    Create sandbox tools bound to a specific thread.

    Args:
        thread_id: Thread identifier for sandbox lookup

    Returns:
        Tuple of (run_code tool, run_command tool)
    """

    @tool
    def run_code(
        code: str,
        language: Literal["python", "bash", "javascript"] = "python",
        timeout_seconds: int = 120
    ) -> str:
        """
        Execute code using the Jupyter-style code interpreter.

        **Use this tool for:**
        - Writing files (use Python's open() or pathlib)
        - Data processing and transformation
        - Complex multi-line operations
        - Any task requiring proper handling of multi-line strings

        **Languages:** python (default), bash, javascript

        **Examples:**

        Write a file:
        ```
        run_code(code='''
        with open("/sandbox/outputs/report.md", "w") as f:
            f.write(\"\"\"# Report Title

        ## Section 1
        Content here with "quotes" and special chars...
        \"\"\")
        print("File written successfully")
        ''')
        ```

        Process data:
        ```
        run_code(code='''
        import json
        data = {"key": "value", "items": [1, 2, 3]}
        with open("/sandbox/outputs/data.json", "w") as f:
            json.dump(data, f, indent=2)
        ''')
        ```

        Args:
            code: Code to execute
            language: python (default), bash, or javascript
            timeout_seconds: Timeout (default 120s, max 600s)

        Returns:
            Execution output (stdout, results, errors)
        """
        sandbox_instance = get_sandbox(thread_id)
        if not sandbox_instance:
            return "Error: Sandbox not initialized for this thread"

        try:
            execution = sandbox_instance.run_code(
                code,
                language=language,
                timeout=min(timeout_seconds, 600)
            )

            # Build output from execution result
            output_parts = []

            # Add stdout/stderr from logs
            if hasattr(execution, 'logs'):
                if execution.logs.stdout:
                    output_parts.extend(execution.logs.stdout)
                if execution.logs.stderr:
                    for err in execution.logs.stderr:
                        output_parts.append(f"[stderr] {err}")

            # Add results if any
            if hasattr(execution, 'results') and execution.results:
                for result in execution.results:
                    if hasattr(result, 'text') and result.text:
                        output_parts.append(f"[result] {result.text}")
                    elif hasattr(result, 'value') and result.value is not None:
                        output_parts.append(f"[result] {result.value}")

            # Add error if present
            if hasattr(execution, 'error') and execution.error:
                error_msg = str(execution.error)
                if hasattr(execution.error, 'name'):
                    error_msg = f"{execution.error.name}: {execution.error.value}"
                output_parts.append(f"[error] {error_msg}")

            output = "\n".join(output_parts)

            # Truncate if too long
            max_length = 30000
            if len(output) > max_length:
                output = output[:max_length] + f"\n... (truncated, {len(output)} total chars)"

            return output or "(no output)"

        except Exception as e:
            return f"Error executing code: {e}"

    @tool
    def run_command(
        command: str,
        timeout_seconds: int = 120
    ) -> str:
        """
        Execute a shell command in the sandbox.

        **Use this tool for:**
        - Quick file operations (ls, cat, head, grep, find)
        - Running existing scripts (python /path/to/script.py)
        - Installing packages (pip install pandas)
        - Simple file reading

        **Do NOT use for:**
        - Writing file content (use run_code with Python instead)
        - Complex bash with heredocs, multi-line strings, or escaping
        - Any operation requiring special character handling

        **Examples:**
        ```
        run_command(command="ls -la /sandbox/skills/")
        run_command(command="cat /sandbox/skills/my-skill/SKILL.md")
        run_command(command="python /sandbox/skills/my-skill/scripts/run.py arg1 arg2")
        run_command(command="pip install pandas openpyxl")
        run_command(command="head -50 /sandbox/outputs/result.md")
        ```

        Args:
            command: Shell command to execute
            timeout_seconds: Timeout (default 120s, max 600s)

        Returns:
            Command output (stdout + stderr)
        """
        sandbox_instance = get_sandbox(thread_id)
        if not sandbox_instance:
            return "Error: Sandbox not initialized for this thread"

        try:
            result = sandbox_instance.commands.run(
                command,
                timeout=min(timeout_seconds, 600)  # Cap at 600s
            )

            # Combine stdout and stderr
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"[stderr] {result.stderr}")

            # Include exit code if non-zero
            if hasattr(result, 'exit_code') and result.exit_code != 0:
                output_parts.append(f"[exit_code] {result.exit_code}")

            output = "\n".join(output_parts)

            # Truncate if too long
            max_length = 30000
            if len(output) > max_length:
                output = output[:max_length] + f"\n... (truncated, {len(output)} total chars)"

            return output or "(no output)"

        except Exception as e:
            return f"Error executing command: {e}"

    return run_code, run_command


# Keep backward compatibility alias
def create_sandbox_tool(thread_id: str):
    """
    DEPRECATED: Use create_sandbox_tools() instead.

    This function is kept for backward compatibility but returns only run_command.
    """
    log.warning("create_sandbox_tool is deprecated, use create_sandbox_tools instead")
    _, run_command = create_sandbox_tools(thread_id)
    return run_command
