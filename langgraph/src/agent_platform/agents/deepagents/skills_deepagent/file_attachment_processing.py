"""File attachment processing for Skills DeepAgent - writes to sandbox.

This module handles transferring user-uploaded files to the E2B sandbox.

Supported formats:
1. <UserUploadedImage> - Binary images downloaded from storage
2. <UserUploadedDocument> - Binary documents downloaded from storage
3. <UserUploadedAttachment> - Legacy text-only format (backwards compatibility)

Files are downloaded from Supabase Storage and written to /sandbox/user_uploads/.
"""

import re
import httpx
from typing import Annotated, Optional, List, Dict, Any
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from agent_platform.sentry import get_logger

try:
    from .state import SkillsDeepAgentState
    from .sandbox_tools import get_sandbox, get_or_create_sandbox
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.state import SkillsDeepAgentState
    from agent_platform.agents.deepagents.skills_deepagent.sandbox_tools import get_sandbox, get_or_create_sandbox

logger = get_logger(__name__)


def _extract_xml_field(content: str, field_name: str) -> Optional[str]:
    """Extract a field value from XML content."""
    pattern = rf'<{field_name}>(.*?)</{field_name}>'
    match = re.search(pattern, content, re.DOTALL)
    return match.group(1).strip() if match else None


def _fetch_signed_urls(
    storage_paths: List[str],
    langconnect_url: str,
    access_token: str,
) -> Dict[str, str]:
    """Fetch signed URLs for multiple storage paths from LangConnect.

    Uses the batch-signed-urls endpoint which generates pre-authenticated
    Supabase Storage URLs. This is the same pattern used by skills download
    and image preprocessing.

    Args:
        storage_paths: List of storage paths (e.g., ["user_id/timestamp_file.xlsx"])
        langconnect_url: LangConnect API URL
        access_token: User's access token for authentication

    Returns:
        Dict mapping storage_path -> signed_url

    Raises:
        Exception if API call fails
    """
    url = f"{langconnect_url}/agent-filesystem/storage/batch-signed-urls"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "storage_paths": storage_paths,
        "expiry_seconds": 1800,  # 30 minutes
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("signed_urls", {})


def _download_from_signed_url(signed_url: str) -> bytes:
    """Download a file directly from a signed URL.

    Args:
        signed_url: Pre-authenticated Supabase Storage URL

    Returns:
        File content as bytes

    Raises:
        Exception if download fails
    """
    with httpx.Client(timeout=60.0) as client:
        response = client.get(signed_url)
        response.raise_for_status()
        return response.content


def _parse_binary_uploads(message_content: str) -> List[Dict[str, Any]]:
    """Parse UserUploadedImage and UserUploadedDocument XML blocks.

    Returns list of dicts with:
    - type: "image" or "document"
    - file_name: Original filename
    - file_type: MIME type
    - storage_path: Path in Supabase Storage
    - sandbox_path: Target path in sandbox
    - preview: Optional text preview (documents only)
    """
    uploads = []

    # Parse UserUploadedImage blocks
    image_pattern = r'<UserUploadedImage[^>]*>(.*?)</UserUploadedImage>'
    for match in re.finditer(image_pattern, message_content, re.DOTALL):
        content = match.group(1)
        file_name = _extract_xml_field(content, 'FileName')
        file_type = _extract_xml_field(content, 'FileType')
        storage_path = _extract_xml_field(content, 'StoragePath')
        sandbox_path = _extract_xml_field(content, 'SandboxPath')

        if file_name and storage_path and sandbox_path:
            uploads.append({
                'type': 'image',
                'file_name': file_name,
                'file_type': file_type or 'image/png',
                'storage_path': storage_path,
                'sandbox_path': sandbox_path,
            })

    # Parse UserUploadedDocument blocks
    doc_pattern = r'<UserUploadedDocument[^>]*>(.*?)</UserUploadedDocument>'
    for match in re.finditer(doc_pattern, message_content, re.DOTALL):
        content = match.group(1)
        file_name = _extract_xml_field(content, 'FileName')
        file_type = _extract_xml_field(content, 'FileType')
        storage_path = _extract_xml_field(content, 'StoragePath')
        sandbox_path = _extract_xml_field(content, 'SandboxPath')
        preview = _extract_xml_field(content, 'Preview')

        if file_name and storage_path and sandbox_path:
            uploads.append({
                'type': 'document',
                'file_name': file_name,
                'file_type': file_type or 'application/octet-stream',
                'storage_path': storage_path,
                'sandbox_path': sandbox_path,
                'preview': preview,
            })

    return uploads


def _parse_legacy_attachments(message_content: str) -> List[Dict[str, Any]]:
    """Parse legacy UserUploadedAttachment XML blocks (text only).

    Returns list of dicts with:
    - type: "legacy"
    - file_name: Original filename
    - file_type: MIME type
    - content: Extracted text content
    """
    attachments = []

    attachment_pattern = r'<UserUploadedAttachment>(.*?)</UserUploadedAttachment>'
    for match in re.finditer(attachment_pattern, message_content, re.DOTALL):
        content = match.group(1)
        file_name = _extract_xml_field(content, 'FileName')
        file_type = _extract_xml_field(content, 'FileType')
        text_content = _extract_xml_field(content, 'Content')

        if file_name and text_content:
            attachments.append({
                'type': 'legacy',
                'file_name': file_name,
                'file_type': file_type or 'text/plain',
                'content': text_content,
            })

    return attachments


def extract_file_attachments_to_sandbox(
    state: Annotated[SkillsDeepAgentState, InjectedState],
    thread_id: str,
    langconnect_url: str = "http://langconnect:8080",
    access_token: Optional[str] = None,
) -> Command:
    """Extract file attachments from messages and write to sandbox.

    Handles three formats:
    1. UserUploadedImage - Downloads binary from storage
    2. UserUploadedDocument - Downloads binary from storage
    3. UserUploadedAttachment - Legacy text-only format

    Files are written to /sandbox/user_uploads/

    Returns Command with empty update (files are in sandbox, not state).
    """
    logger.info("[SKILLS_FILE_ATTACH] Starting file attachment extraction for thread: %s", thread_id)

    messages = state.get("messages", [])
    if not messages:
        logger.info("[SKILLS_FILE_ATTACH] No messages in state")
        return Command(update={})

    latest_message = messages[-1]
    logger.info("[SKILLS_FILE_ATTACH] Latest message type: %s", type(latest_message).__name__)

    if not isinstance(latest_message, HumanMessage):
        logger.info("[SKILLS_FILE_ATTACH] Latest message is not HumanMessage, skipping")
        return Command(update={})

    # Collect all text content from the message
    message_texts = []

    logger.info("[SKILLS_FILE_ATTACH] Message content type: %s", type(latest_message.content).__name__)

    if isinstance(latest_message.content, str):
        message_texts.append(latest_message.content)
        logger.info("[SKILLS_FILE_ATTACH] Content is string, length: %d", len(latest_message.content))
    elif isinstance(latest_message.content, list):
        logger.info("[SKILLS_FILE_ATTACH] Content is list with %d items", len(latest_message.content))
        for i, content_item in enumerate(latest_message.content):
            logger.info("[SKILLS_FILE_ATTACH] Item %d: type=%s", i, type(content_item).__name__)
            if isinstance(content_item, dict):
                item_type = content_item.get('type', 'unknown')
                logger.info("[SKILLS_FILE_ATTACH] Item %d is dict with type=%s", i, item_type)
                if item_type == 'text':
                    text = content_item.get('text', '')
                    message_texts.append(text)
                    # Log first 200 chars of text to help debug
                    preview = text[:200] if len(text) > 200 else text
                    logger.info("[SKILLS_FILE_ATTACH] Item %d text preview: %s", i, preview)

    message_content = '\n'.join(message_texts)
    logger.info("[SKILLS_FILE_ATTACH] Combined message content length: %d", len(message_content))

    # Check for any upload markers
    has_binary_uploads = '<UserUploadedImage' in message_content or '<UserUploadedDocument' in message_content
    has_legacy_attachments = '<UserUploadedAttachment>' in message_content

    logger.info("[SKILLS_FILE_ATTACH] has_binary_uploads=%s, has_legacy_attachments=%s",
                has_binary_uploads, has_legacy_attachments)

    if not has_binary_uploads and not has_legacy_attachments:
        logger.info("[SKILLS_FILE_ATTACH] No file attachments found in message")
        return Command(update={})

    # Get sandbox for this thread
    sandbox = get_sandbox(thread_id)
    if not sandbox:
        logger.warning("[SKILLS_FILE_ATTACH] No sandbox available for uploads (thread: %s)", thread_id)
        return Command(update={})

    # Ensure user_uploads directory exists
    try:
        sandbox.files.make_dir("/sandbox/user_uploads")
    except Exception:
        pass  # May already exist

    files_written = 0

    # Process binary uploads (images and documents) using signed URL pattern
    # This follows the same approach as skills download (fetch_skill_zip)
    if has_binary_uploads and access_token:
        binary_uploads = _parse_binary_uploads(message_content)

        if binary_uploads:
            # Step 1: Collect all storage paths and batch fetch signed URLs
            storage_paths = [upload['storage_path'] for upload in binary_uploads]
            logger.info(
                "[SKILLS_FILE_ATTACH] Fetching signed URLs for %d files: %s",
                len(storage_paths),
                storage_paths
            )

            try:
                signed_urls = _fetch_signed_urls(
                    storage_paths=storage_paths,
                    langconnect_url=langconnect_url,
                    access_token=access_token,
                )
                logger.info(
                    "[SKILLS_FILE_ATTACH] Got %d signed URLs",
                    len(signed_urls)
                )
            except Exception as e:
                logger.error(
                    "[SKILLS_FILE_ATTACH] Failed to fetch signed URLs: %s",
                    str(e)
                )
                signed_urls = {}

            # Step 2: Download from signed URLs and write to sandbox
            for upload in binary_uploads:
                storage_path = upload['storage_path']
                signed_url = signed_urls.get(storage_path)

                if not signed_url:
                    logger.warning(
                        "[SKILLS_FILE_ATTACH] No signed URL for %s - skipping",
                        upload['file_name']
                    )
                    continue

                try:
                    # Download directly from signed URL (no auth needed)
                    file_data = _download_from_signed_url(signed_url)

                    # Write to sandbox
                    sandbox.files.write(upload['sandbox_path'], file_data)
                    logger.info(
                        "[SKILLS_FILE_ATTACH] Wrote %s to %s (%d bytes)",
                        upload['file_name'],
                        upload['sandbox_path'],
                        len(file_data)
                    )
                    files_written += 1

                except Exception as e:
                    logger.error(
                        "[SKILLS_FILE_ATTACH] Failed to transfer %s: %s",
                        upload['file_name'],
                        str(e)
                    )

    elif has_binary_uploads and not access_token:
        logger.warning(
            "[SKILLS_FILE_ATTACH] Binary uploads found but no access token - cannot download from storage"
        )

    # Process legacy attachments (text only, for backwards compatibility)
    if has_legacy_attachments:
        legacy_attachments = _parse_legacy_attachments(message_content)

        for attachment in legacy_attachments:
            try:
                # Write text content as markdown file
                markdown_file_name = f"{attachment['file_name']}.md"
                sandbox_path = f"/sandbox/user_uploads/{markdown_file_name}"

                sandbox.files.write(sandbox_path, attachment['content'].encode('utf-8'))
                logger.info(
                    "[SKILLS_FILE_ATTACH] Wrote legacy attachment %s to %s",
                    attachment['file_name'],
                    sandbox_path
                )
                files_written += 1

            except Exception as e:
                logger.error(
                    "[SKILLS_FILE_ATTACH] Failed to write legacy attachment %s: %s",
                    attachment['file_name'],
                    str(e)
                )

    logger.info("[SKILLS_FILE_ATTACH] Extracted %d file(s) to sandbox", files_written)

    # Return empty update - files are in sandbox, not state
    return Command(update={})


def create_file_attachment_node(
    thread_id: str,
    langconnect_url: str = "http://langconnect:8080",
    access_token: Optional[str] = None,
    skills: Optional[List[Dict[str, Any]]] = None,
    sandbox_pip_packages: Optional[List[str]] = None,
    sandbox_timeout: int = 3600,
):
    """Create a file attachment processing node that also initializes sandbox.

    This node runs first in the graph and handles:
    1. Sandbox initialization (with reconnection support via state.sandbox_id)
    2. File attachment extraction to sandbox

    Args:
        thread_id: Thread identifier for sandbox
        langconnect_url: LangConnect API URL for storage/skill downloads
        access_token: User's access token for authentication
        skills: List of skill references to upload to sandbox
        sandbox_pip_packages: Additional pip packages to install
        sandbox_timeout: Sandbox timeout in seconds (max 3600 for hobby tier)

    Returns a function that can be used as a LangGraph node.
    """

    async def file_attachment_node(state: SkillsDeepAgentState) -> Command:
        """Initialize sandbox and process file attachments.

        This is an async function because get_or_create_sandbox is async.
        Returns Command with sandbox_id update for state persistence.
        """
        # 1. Initialize sandbox (with reconnection support)
        # Read existing sandbox_id from state for reconnection
        existing_sandbox_id = state.get("sandbox_id")

        if existing_sandbox_id:
            logger.info(
                "[SKILLS_FILE_ATTACH] Found existing sandbox_id in state: %s",
                existing_sandbox_id
            )
        else:
            logger.info("[SKILLS_FILE_ATTACH] No existing sandbox_id in state, will create new sandbox")

        try:
            # get_or_create_sandbox now returns (sandbox, sandbox_id)
            # It will try to reconnect if existing_sandbox_id is provided
            sandbox, sandbox_id = await get_or_create_sandbox(
                thread_id=thread_id,
                skills=skills or [],
                langconnect_url=langconnect_url,
                access_token=access_token,
                pip_packages=sandbox_pip_packages,
                timeout=sandbox_timeout,
                existing_sandbox_id=existing_sandbox_id,
            )
            logger.info(
                "[SKILLS_FILE_ATTACH] Sandbox ready: %s (reconnected=%s)",
                sandbox_id,
                sandbox_id == existing_sandbox_id
            )
        except Exception as e:
            logger.error("[SKILLS_FILE_ATTACH] Failed to initialize sandbox: %s", e)
            raise RuntimeError(f"Sandbox initialization failed: {e}")

        # 2. Process file attachments (rest of the original logic)
        # Now that sandbox is initialized, process attachments
        messages = state.get("messages", [])
        files_written = 0

        if messages:
            latest_message = messages[-1]

            if isinstance(latest_message, HumanMessage):
                # Collect all text content from the message
                message_texts = []

                if isinstance(latest_message.content, str):
                    message_texts.append(latest_message.content)
                elif isinstance(latest_message.content, list):
                    for content_item in latest_message.content:
                        if isinstance(content_item, dict) and content_item.get('type') == 'text':
                            message_texts.append(content_item.get('text', ''))

                message_content = '\n'.join(message_texts)

                # Check for upload markers
                has_binary_uploads = '<UserUploadedImage' in message_content or '<UserUploadedDocument' in message_content
                has_legacy_attachments = '<UserUploadedAttachment>' in message_content

                if has_binary_uploads or has_legacy_attachments:
                    # Ensure user_uploads directory exists
                    try:
                        sandbox.files.make_dir("/sandbox/user_uploads")
                    except Exception:
                        pass

                    # Process binary uploads
                    if has_binary_uploads and access_token:
                        binary_uploads = _parse_binary_uploads(message_content)
                        if binary_uploads:
                            storage_paths = [upload['storage_path'] for upload in binary_uploads]
                            try:
                                signed_urls = _fetch_signed_urls(
                                    storage_paths=storage_paths,
                                    langconnect_url=langconnect_url,
                                    access_token=access_token,
                                )
                            except Exception as e:
                                logger.error("[SKILLS_FILE_ATTACH] Failed to fetch signed URLs: %s", e)
                                signed_urls = {}

                            for upload in binary_uploads:
                                signed_url = signed_urls.get(upload['storage_path'])
                                if signed_url:
                                    try:
                                        file_data = _download_from_signed_url(signed_url)
                                        sandbox.files.write(upload['sandbox_path'], file_data)
                                        logger.info(
                                            "[SKILLS_FILE_ATTACH] Wrote %s to %s (%d bytes)",
                                            upload['file_name'],
                                            upload['sandbox_path'],
                                            len(file_data)
                                        )
                                        files_written += 1
                                    except Exception as e:
                                        logger.error(
                                            "[SKILLS_FILE_ATTACH] Failed to transfer %s: %s",
                                            upload['file_name'],
                                            str(e)
                                        )

                    # Process legacy attachments
                    if has_legacy_attachments:
                        legacy_attachments = _parse_legacy_attachments(message_content)
                        for attachment in legacy_attachments:
                            try:
                                markdown_file_name = f"{attachment['file_name']}.md"
                                sandbox_path = f"/sandbox/user_uploads/{markdown_file_name}"
                                sandbox.files.write(sandbox_path, attachment['content'].encode('utf-8'))
                                files_written += 1
                            except Exception as e:
                                logger.error(
                                    "[SKILLS_FILE_ATTACH] Failed to write legacy attachment: %s",
                                    str(e)
                                )

        logger.info(
            "[SKILLS_FILE_ATTACH] Completed: sandbox_id=%s, files_written=%d",
            sandbox_id,
            files_written
        )

        # Return sandbox_id in state for persistence across requests
        return Command(update={"sandbox_id": sandbox_id})

    return file_attachment_node
