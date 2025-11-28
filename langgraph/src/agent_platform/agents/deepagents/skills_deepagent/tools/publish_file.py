"""Publish file tool for Skills DeepAgent.

This tool allows agents to explicitly publish files from the sandbox
to make them available for user preview and download.
"""

import json
import logging
import os
from datetime import datetime
from typing import Annotated, Any, Callable, Optional

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

try:
    from ..state import PublishedFile
    from ..sandbox_tools import get_sandbox
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.state import PublishedFile
    from agent_platform.agents.deepagents.skills_deepagent.sandbox_tools import get_sandbox

logger = logging.getLogger(__name__)

# MIME types by file extension
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".html": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def create_publish_file_tool(
    thread_id: str,
    user_id: str,
    langconnect_url: str,
    access_token: str,
):
    """Create publish_file_to_user tool bound to thread context.

    Args:
        thread_id: Thread identifier for storage path
        user_id: User identifier for storage path
        langconnect_url: Base URL of LangConnect API
        access_token: Supabase access token for uploads

    Returns:
        Tool function that can publish files from sandbox to storage
    """

    @tool
    def publish_file_to_user(
        file_path: str,
        display_name: str,
        description: str = "",
        tool_call_id: Annotated[str, InjectedToolCallId] = None
    ) -> Command:
        """
        Make a file from the sandbox available to the user for preview and download.

        This uploads the file from the sandbox to permanent storage and displays
        a download card in the chat. Use when you've created a file the user needs.

        If you publish a file with the same display_name as before, it updates
        that file (useful for revisions).

        Args:
            file_path: Path to the file in sandbox (e.g., /sandbox/outputs/report.docx)
            display_name: User-friendly name shown in UI (e.g., "Quarterly Report")
            description: Brief description of what the file contains

        Returns:
            Confirmation with file metadata

        Examples:
            publish_file_to_user(
                file_path="/sandbox/outputs/analysis.docx",
                display_name="Market Analysis Report",
                description="Comprehensive analysis of Q3 market trends"
            )
        """
        try:
            # 1. Get sandbox and read file
            sandbox = get_sandbox(thread_id)
            if not sandbox:
                return _error_response(
                    tool_call_id,
                    "Sandbox not initialized for this thread"
                )

            # Read file content from sandbox as bytes (critical for binary files like docx, xlsx, pdf)
            # Convert bytearray to bytes for httpx multipart upload compatibility
            try:
                file_content = bytes(sandbox.files.read(file_path, format="bytes"))
            except Exception as e:
                return _error_response(
                    tool_call_id,
                    f"Failed to read file from sandbox: {str(e)}"
                )

            # 2. Determine file metadata
            filename = os.path.basename(file_path)
            extension = os.path.splitext(filename)[1].lower()
            mime_type = MIME_TYPES.get(extension, "application/octet-stream")
            file_size = len(file_content)

            # 3. Upload to storage via LangConnect
            # Storage path format: {user_id}/{thread_id}/{filename}
            storage_path = f"{user_id}/{thread_id}/{filename}"

            try:
                upload_url = f"{langconnect_url}/storage/upload-agent-output"

                # Use httpx for synchronous upload
                with httpx.Client() as client:
                    response = client.post(
                        upload_url,
                        headers={"Authorization": f"Bearer {access_token}"},
                        files={"file": (filename, file_content, mime_type)},
                        data={
                            "thread_id": thread_id,
                            "filename": filename,
                        },
                        timeout=60.0
                    )
                    response.raise_for_status()
                    upload_result = response.json()
                    storage_path = upload_result.get("storage_path", storage_path)

            except Exception as e:
                logger.error(f"Failed to upload file to storage: {e}")
                return _error_response(
                    tool_call_id,
                    f"Failed to upload file to storage: {str(e)}"
                )

            # 4. Build published file entry
            published_file: PublishedFile = {
                "display_name": display_name,
                "description": description,
                "filename": filename,
                "file_type": extension,
                "mime_type": mime_type,
                "file_size": file_size,
                "storage_path": storage_path,
                "sandbox_path": file_path,
                "published_at": datetime.utcnow().isoformat()
            }

            # 5. Return Command that updates state AND sends tool message
            logger.info(f"Published file '{display_name}' ({filename}) to storage: {storage_path}")

            return Command(
                update={
                    "published_files": [published_file],  # Reducer handles merge
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "success": True,
                                "display_name": display_name,
                                "description": description,
                                "filename": filename,
                                "file_type": extension,
                                "file_size": file_size,
                                "storage_path": storage_path
                            }),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )

        except Exception as e:
            logger.error(f"Error in publish_file_to_user: {e}")
            return _error_response(tool_call_id, str(e))

    return publish_file_to_user


def _error_response(tool_call_id: str, error_message: str) -> Command:
    """Create an error response Command."""
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "success": False,
                        "error": error_message
                    }),
                    tool_call_id=tool_call_id
                )
            ]
        }
    )
