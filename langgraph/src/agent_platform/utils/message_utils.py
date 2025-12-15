"""
Message processing utilities for LangGraph agents.

This module provides utilities for:
1. Cleaning orphaned tool calls from message history
2. Converting storage paths to signed URLs in image content blocks
3. Local dev fallback: Converting HTTP URLs to base64 data URLs for Claude API
4. Converting collection_read_image tool results to multimodal content blocks
"""

import re
import json
from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, HumanMessage
from langchain_core.messages.utils import filter_messages
from agent_platform.sentry import get_logger
import httpx

logger = get_logger(__name__)


# ==================== Tool Call Cleaning ====================

def clean_orphaned_tool_calls(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Remove AI messages with tool calls that have no corresponding tool messages,
    and tool messages that have no corresponding AI message tool calls.

    This prevents OpenAI API errors that occur when an AI message with tool_calls
    is not followed by corresponding ToolMessage responses. This commonly happens
    during human-in-the-loop interrupts where tool calls are approved/rejected
    but never executed.

    Args:
        messages: List of BaseMessage objects to clean

    Returns:
        List of BaseMessage objects with orphaned tool calls removed

    Example:
        >>> from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
        >>> messages = [
        ...     HumanMessage(content="Calculate 2+2"),
        ...     AIMessage(content="", tool_calls=[{"id": "call_123", "name": "calc", "args": {}}]),
        ...     HumanMessage(content="Actually never mind")  # No ToolMessage response!
        ... ]
        >>> cleaned = clean_orphaned_tool_calls(messages)
        >>> # The AIMessage with orphaned tool_calls will be removed
    """
    if not messages:
        return messages

    # Build sets of tool call IDs
    tool_call_ids_made = set()
    tool_call_ids_responded = set()

    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_call_ids_made.add(tool_call["id"])
        elif isinstance(message, ToolMessage):
            tool_call_ids_responded.add(message.tool_call_id)

    # Find orphaned IDs
    orphaned_tool_call_ids = tool_call_ids_made - tool_call_ids_responded
    orphaned_tool_message_ids = tool_call_ids_responded - tool_call_ids_made
    all_orphaned_ids = orphaned_tool_call_ids | orphaned_tool_message_ids

    if all_orphaned_ids:
        cleaned_messages = filter_messages(
            messages,
            exclude_tool_calls=list(all_orphaned_ids)
        )
        logger.debug(
            "[CLEAN_MESSAGES] Filtered %d orphaned tool calls from %d messages",
            len(all_orphaned_ids), len(messages)
        )
        return cleaned_messages

    return messages


# ==================== Orphaned Tool Call Resolution ====================

# Standard content for cancelled tool messages - frontend can detect this
CANCELLED_TOOL_CALL_CONTENT = json.dumps({
    "status": "cancelled",
    "message": "Tool execution was cancelled before completion."
})


def resolve_orphaned_tool_calls(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Resolve orphaned tool calls by inserting synthetic ToolMessages for cancelled calls.

    Instead of removing orphaned tool calls (which leaves UI in loading state),
    this function inserts ToolMessages with cancellation status, allowing:
    - API compatibility (every tool_call has a ToolMessage)
    - UI to render "cancelled" state instead of infinite spinner

    This also cleans up malformed tool calls (e.g., empty names) that would cause API errors.

    This commonly happens during thread cancellation where tool calls are made
    but the thread is cancelled before tool execution completes.

    Args:
        messages: List of BaseMessage objects to process

    Returns:
        List with synthetic ToolMessages inserted after AIMessages with orphaned tool_calls,
        and malformed tool calls removed from AIMessages.

    Example:
        >>> from langchain_core.messages import AIMessage, HumanMessage
        >>> messages = [
        ...     HumanMessage(content="Search for cats"),
        ...     AIMessage(content="", tool_calls=[{"id": "call_123", "name": "search", "args": {}}]),
        ...     HumanMessage(content="Actually, cancel that")  # No ToolMessage response!
        ... ]
        >>> resolved = resolve_orphaned_tool_calls(messages)
        >>> # A synthetic ToolMessage with cancelled status will be inserted
    """
    if not messages:
        return messages

    # Build sets of tool call IDs and response IDs
    tool_call_ids_made = {}  # id -> (tool_name, index of AIMessage)
    tool_call_ids_responded = {}  # id -> index of ToolMessage
    malformed_tool_call_ids = set()
    malformed_tool_call_count = 0
    out_of_order_tool_message_ids = set()

    for i, message in enumerate(messages):
        if isinstance(message, AIMessage) and message.tool_calls:
            for j, tool_call in enumerate(message.tool_calls):
                tool_name = tool_call.get("name", "")
                tool_id = tool_call.get("id", "")

                if not tool_name or not tool_id:
                    malformed_tool_call_count += 1
                    malformed_tool_call_ids.add(tool_id or f"malformed-{i}-{j}")
                else:
                    tool_call_ids_made[tool_id] = (tool_name, i)
        elif isinstance(message, ToolMessage):
            tool_call_ids_responded[message.tool_call_id] = i

    # Find orphaned and out-of-order tool calls
    orphaned_ids = set(tool_call_ids_made.keys()) - set(tool_call_ids_responded.keys())
    orphaned_tool_message_ids = set(tool_call_ids_responded.keys()) - set(tool_call_ids_made.keys())

    # Find out-of-order ToolMessages (come BEFORE their AIMessage)
    for tool_call_id, tool_msg_index in tool_call_ids_responded.items():
        if tool_call_id in tool_call_ids_made:
            ai_msg_index = tool_call_ids_made[tool_call_id][1]
            if tool_msg_index < ai_msg_index:
                out_of_order_tool_message_ids.add(tool_call_id)

    # Treat out-of-order tool_calls as orphaned (need synthetic responses)
    if out_of_order_tool_message_ids:
        orphaned_ids = orphaned_ids | out_of_order_tool_message_ids

    has_issues = (
        len(orphaned_ids) > 0 or
        malformed_tool_call_count > 0 or
        len(orphaned_tool_message_ids) > 0 or
        len(out_of_order_tool_message_ids) > 0
    )

    if not has_issues:
        return messages

    # Build new message list with fixes applied
    valid_tool_call_ids = set(tool_call_ids_made.keys())
    result = []
    synthetic_inserted = 0
    orphaned_removed = 0
    out_of_order_removed = 0

    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            # Filter out malformed tool calls
            valid_tool_calls = [
                tc for tc in message.tool_calls
                if tc.get("name") and tc.get("id")
            ]

            # Rebuild message if we filtered any tool calls
            if len(valid_tool_calls) != len(message.tool_calls):
                if valid_tool_calls:
                    result.append(AIMessage(
                        content=message.content,
                        tool_calls=valid_tool_calls,
                        id=message.id,
                    ))
                elif message.content:
                    result.append(AIMessage(content=message.content, id=message.id))
            else:
                result.append(message)

            # Insert synthetic responses for orphaned tool calls
            for tool_call in valid_tool_calls:
                if tool_call["id"] in orphaned_ids:
                    result.append(ToolMessage(
                        content=CANCELLED_TOOL_CALL_CONTENT,
                        tool_call_id=tool_call["id"],
                        name=tool_call.get("name", "unknown"),
                    ))
                    synthetic_inserted += 1

        elif isinstance(message, ToolMessage):
            # Skip orphaned or out-of-order ToolMessages
            if message.tool_call_id not in valid_tool_call_ids:
                orphaned_removed += 1
                continue
            if message.tool_call_id in out_of_order_tool_message_ids:
                out_of_order_removed += 1
                continue
            result.append(message)

        else:
            result.append(message)

    # Single summary log for all changes
    if synthetic_inserted > 0 or orphaned_removed > 0 or out_of_order_removed > 0 or malformed_tool_call_count > 0:
        logger.info(
            "[RESOLVE_ORPHANS] Fixed %d messages: inserted=%d cancelled, removed=%d orphaned/%d out-of-order, filtered=%d malformed",
            len(messages) - len(result) + synthetic_inserted,
            synthetic_inserted,
            orphaned_removed,
            out_of_order_removed,
            malformed_tool_call_count
        )

    return result


def create_orphan_resolution_hook():
    """
    Create a pre-model hook that resolves orphaned tool calls with synthetic responses.

    This hook should be applied FIRST in the hook chain (before trimming and image processing)
    to ensure all subsequent hooks see a valid message sequence.

    Usage:
        orphan_hook = create_orphan_resolution_hook()

        # Compose with other hooks
        async def combined_hook(state, config):
            state = {**state, **orphan_hook(state)}  # Resolve orphans first
            state = {**state, **trimming_hook(state)}
            state = await image_hook(state, config)
            return state

    Returns:
        Sync hook function compatible with pre_model_hook composition
    """
    def orphan_resolution_hook(state):
        """Resolve orphaned tool calls before model invocation."""
        # Check for llm_input_messages first (set by other hooks), fall back to messages
        messages_key = "llm_input_messages" if "llm_input_messages" in state else "messages"
        messages = state.get(messages_key, [])

        if not messages:
            return state

        try:
            resolved_messages = resolve_orphaned_tool_calls(messages)
            return {"llm_input_messages": resolved_messages}
        except Exception as e:
            logger.exception("[ORPHAN_HOOK] Error resolving orphaned tool calls: %s", e)
            # On error, return original state to prevent breaking the agent
            return state

    return orphan_resolution_hook


# ==================== collection_read_image Tool Result Processing ====================

async def convert_collection_read_image_to_multimodal(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Convert collection_read_image tool results from JSON strings to multimodal content blocks.

    The collection_read_image tool returns a JSON string containing image description and signed URL.
    This function detects those ToolMessages and converts them to multimodal content with:
    - Text description
    - Image content block with the signed URL (converted to base64 if HTTP for local dev)

    This allows vision-enabled LLMs to actually see the images, not just read descriptions.

    Args:
        messages: List of BaseMessage objects to process

    Returns:
        List of BaseMessage objects with collection_read_image results converted to multimodal content

    Example:
        >>> # ToolMessage with JSON content becomes multimodal
        >>> before = ToolMessage(
        ...     content='{"description": "A cat", "metadata": {"signed_url": "https://..."}}',
        ...     name="collection_read_image",
        ...     tool_call_id="call_123"
        ... )
        >>> after = await convert_collection_read_image_to_multimodal([before])
        >>> # Now content is: [
        >>> #   {"type": "text", "text": "A cat"},
        >>> #   {"type": "image_url", "image_url": {"url": "https://..."}}
        >>> # ]
    """
    if not messages:
        return messages

    processed_messages = []
    for message in messages:
        # Only process ToolMessages from collection_read_image
        if not isinstance(message, ToolMessage):
            processed_messages.append(message)
            continue

        # Check if this is from collection_read_image tool
        if message.name != "collection_read_image":
            processed_messages.append(message)
            continue

        # Try to parse the JSON content
        try:
            # Content should be a JSON string
            if not isinstance(message.content, str):
                processed_messages.append(message)
                continue

            data = json.loads(message.content)

            # Extract description and signed URL
            description = data.get("description", "")
            signed_url = data.get("metadata", {}).get("signed_url")
            name = data.get("metadata", {}).get("name", "Image")

            if not signed_url:
                logger.debug("[COLLECTION_READ_IMAGE] No signed_url found in tool result")
                processed_messages.append(message)
                continue

            # Fix localhost URL issue (kong:8000 -> localhost:8000)
            if "kong:8000" in signed_url:
                signed_url = signed_url.replace("kong:8000", "localhost:8000")

            # Convert HTTP URLs to base64 for local development (Claude requires HTTPS)
            if signed_url.startswith("http://"):
                data_url = await convert_http_url_to_base64(signed_url)
                if data_url:
                    signed_url = data_url
                else:
                    logger.warning("[COLLECTION_READ_IMAGE] Failed to convert HTTP URL to base64")

            # Create multimodal content blocks
            multimodal_content = [
                {
                    "type": "text",
                    "text": f"**{name}**\n\n{description}"
                },
                {
                    "type": "image_url",
                    "image_url": {"url": signed_url}
                }
            ]

            # Create new ToolMessage with multimodal content
            processed_msg = ToolMessage(
                content=multimodal_content,
                name=message.name,
                tool_call_id=message.tool_call_id,
                id=message.id,
                additional_kwargs=message.additional_kwargs
            )

            processed_messages.append(processed_msg)

        except (json.JSONDecodeError, KeyError, TypeError):
            processed_messages.append(message)
            continue

    return processed_messages


# ==================== Image Storage Path Processing ====================

# Regex pattern to detect storage paths in the following format:
# {uuid}/{timestamp}_{filename}
# Examples:
#   - Collections: "123e4567-e89b-12d3-a456-426614174000/1703001234_image.png"
#   - Chat uploads: "456e7890-abcd-1234-efgh-567890abcdef/20250126_143022_123456_photo.jpg"
STORAGE_PATH_PATTERN = re.compile(
    r'\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/'  # UUID (collection_id or user_id)
    r'(\d+_[^/\s]+\.(?:png|jpg|jpeg|gif|webp|bmp|tiff))\b',  # Timestamp and filename
    re.IGNORECASE
)


def detect_image_format(image_data: bytes) -> str:
    """
    Detect image format from magic bytes (file signatures).

    This is more reliable than trusting HTTP content-type headers,
    which may be incorrect in the database.

    Args:
        image_data: Raw image bytes

    Returns:
        MIME type string (e.g., "image/png", "image/jpeg")

    Magic bytes reference:
        - PNG: 89 50 4E 47 0D 0A 1A 0A (‰PNG...)
        - JPEG: FF D8 FF
        - GIF: 47 49 46 38 37 61 or 47 49 46 38 39 61 (GIF87a or GIF89a)
        - WebP: 52 49 46 46 ... 57 45 42 50 (RIFF...WEBP)
        - BMP: 42 4D (BM)
    """
    if not image_data or len(image_data) < 12:
        return "image/png"  # Safe fallback

    # PNG: Starts with ‰PNG\r\n\x1a\n
    if image_data.startswith(b'\x89PNG\r\n\x1a\n'):
        return "image/png"

    # JPEG: Starts with FF D8 FF
    elif image_data.startswith(b'\xff\xd8\xff'):
        return "image/jpeg"

    # GIF: Starts with GIF87a or GIF89a
    elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
        return "image/gif"

    # WebP: RIFF container with WEBP at bytes 8-12
    elif len(image_data) > 12 and image_data[8:12] == b'WEBP':
        return "image/webp"

    # BMP: Starts with BM
    elif image_data.startswith(b'BM'):
        return "image/bmp"

    # TIFF: Starts with II (little-endian) or MM (big-endian)
    elif image_data.startswith(b'II\x2a\x00') or image_data.startswith(b'MM\x00\x2a'):
        return "image/tiff"

    else:
        logger.debug("[IMAGE_FORMAT] Unknown magic bytes: %s, defaulting to PNG", image_data[:8].hex())
        return "image/png"  # Safe fallback


async def convert_http_url_to_base64(url: str) -> Optional[str]:
    """
    Convert an HTTP URL to a base64 data URL.

    This is used as a fallback for local development where storage URLs
    use HTTP instead of HTTPS. Claude's API requires HTTPS URLs, so we
    convert local HTTP URLs to base64 data URLs.

    Args:
        url: HTTP URL to convert

    Returns:
        data URL string (data:image/...;base64,...) or None on error
    """
    try:
        import base64

        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

            # Get image data
            image_data = response.content

            # Detect actual format from magic bytes (don't trust HTTP header!)
            content_type = detect_image_format(image_data)

            # Convert to base64
            base64_data = base64.b64encode(image_data).decode('utf-8')

            # Create data URL
            data_url = f"data:{content_type};base64,{base64_data}"
            logger.debug("[MESSAGE_UTILS] Converted HTTP URL to base64: %d bytes", len(image_data))
            return data_url

    except Exception as e:
        logger.warning("[MESSAGE_UTILS] Failed to convert HTTP URL to base64: %s", str(e)[:100])
        return None


async def batch_generate_signed_urls(
    storage_paths: List[str],
    access_token: str,
    langconnect_api_url: str,
    expiry_seconds: int = 1800
) -> Dict[str, str]:
    """
    Generate signed URLs for multiple storage paths in batch.

    Args:
        storage_paths: List of storage paths to convert
        access_token: Supabase JWT token
        langconnect_api_url: Base URL of LangConnect API
        expiry_seconds: URL expiry time (default 30 minutes)

    Returns:
        Dict mapping storage_path -> signed_url
    """
    if not storage_paths:
        return {}

    # Remove duplicates
    unique_paths = list(set(storage_paths))

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{langconnect_api_url}/agent-filesystem/storage/batch-signed-urls",
                json={
                    "storage_paths": unique_paths,
                    "expiry_seconds": expiry_seconds
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            signed_urls = data.get("signed_urls", {})

            if signed_urls:
                logger.debug("[MESSAGE_UTILS] Generated %d signed URLs", len(signed_urls))
            else:
                logger.warning("[MESSAGE_UTILS] API returned no signed URLs")

            return signed_urls

    except Exception as e:
        logger.warning("[MESSAGE_UTILS] Failed to batch generate signed URLs: %s", str(e)[:100])
        return {}


def extract_storage_path_from_metadata(block: dict) -> str:
    """
    Extract storage path from a content block's metadata.

    This is used as a fallback when the URL has been replaced with a signed URL
    or data URL, but the original storage_path is preserved in metadata.

    Args:
        block: Content block dictionary

    Returns:
        Storage path string, or empty string if not found
    """
    metadata = block.get("metadata", {})
    if isinstance(metadata, dict):
        storage_path = metadata.get("storage_path", "")
        if storage_path and STORAGE_PATH_PATTERN.match(storage_path):
            return storage_path
    return ""


def extract_storage_paths_from_content(content: Any) -> List[str]:
    """
    Extract storage paths from message content.

    IMPORTANT: Only extracts from IMAGE CONTENT BLOCKS, not from text blocks.
    This ensures we only replace URLs where the LLM needs to actually view the image.

    Strategy:
    ---------
    1. First, try to extract from the URL field (for new messages with storage paths)
    2. If URL is already converted (starts with http/data), check metadata for original storage_path
    3. This ensures we can re-convert images on every invocation, even historical messages

    Supported Formats:
    ------------------
    1. LangChain standard: {"type": "image", "source_type": "url", "url": "...", "metadata": {"storage_path": "..."}}
    2. OpenAI style: {"type": "image_url", "image_url": {"url": "..."}, "metadata": {"storage_path": "..."}}

    Args:
        content: Message content (string or list of content blocks)

    Returns:
        List of storage paths found in image blocks
    """
    paths = []

    # Only process multimodal content (list of blocks)
    if not isinstance(content, list):
        return paths

    for block in content:
        if not isinstance(block, dict):
            continue

        # LangChain standard format: {"type": "image", "source_type": "url", "url": "..."}
        if block.get("type") == "image" and block.get("source_type") == "url":
            url = block.get("url", "")

            # Try to extract from URL first (for new messages with storage paths)
            if url and not url.startswith("http") and not url.startswith("data:"):
                # This might be a storage path
                matches = STORAGE_PATH_PATTERN.findall(url)
                # Matches are tuples: (uuid, filename)
                for match in matches:
                    uuid, filename = match
                    # Storage path format: uuid/filename
                    paths.append(f"{uuid}/{filename}")
                # Also check if the entire URL is a storage path
                if STORAGE_PATH_PATTERN.match(url):
                    paths.append(url)

            # If URL is already converted, try metadata (for historical messages)
            elif url and (url.startswith("http") or url.startswith("data:")):
                storage_path = extract_storage_path_from_metadata(block)
                if storage_path:
                    paths.append(storage_path)

        # OpenAI style format: {"type": "image_url", "image_url": {"url": "..."}}
        elif block.get("type") == "image_url":
            image_url_obj = block.get("image_url", {})
            if isinstance(image_url_obj, dict):
                url = image_url_obj.get("url", "")

                # Try to extract from URL first
                if url and not url.startswith("http") and not url.startswith("data:"):
                    # This might be a storage path
                    matches = STORAGE_PATH_PATTERN.findall(url)
                    # Matches are tuples: (uuid, filename)
                    for match in matches:
                        uuid, filename = match
                        # Storage path format: uuid/filename
                        paths.append(f"{uuid}/{filename}")
                    # Also check if the entire URL is a storage path
                    if STORAGE_PATH_PATTERN.match(url):
                        paths.append(url)

                # If URL is already converted, try metadata
                elif url and (url.startswith("http") or url.startswith("data:")):
                    storage_path = extract_storage_path_from_metadata(block)
                    if storage_path:
                        paths.append(storage_path)

    return paths


def replace_storage_paths_in_content(content: Any, url_mapping: Dict[str, str]) -> Any:
    """
    Replace storage paths with signed URLs in message content.

    IMPORTANT: Only replaces in IMAGE CONTENT BLOCKS, not in text blocks.
    Text references to storage paths are left completely untouched.

    Strategy:
    ---------
    1. For new messages: Replace storage_path in URL field
    2. For historical messages: Check metadata for storage_path and replace if found
    3. This ensures ALL images get fresh URLs on every invocation

    Args:
        content: Message content (string or list of content blocks)
        url_mapping: Dict mapping storage_path -> signed_url

    Returns:
        Content with storage paths replaced by signed URLs in image blocks only
    """
    if not url_mapping:
        return content

    # Only process multimodal content (list of blocks)
    if not isinstance(content, list):
        return content

    # Process content blocks
    modified_blocks = []
    for block in content:
        if not isinstance(block, dict):
            modified_blocks.append(block)
            continue

        # Create a deep copy to ensure metadata is preserved properly
        modified_block = block.copy()
        if "metadata" in block and isinstance(block["metadata"], dict):
            modified_block["metadata"] = block["metadata"].copy()

        # LangChain standard format: {"type": "image", "source_type": "url", "url": "..."}
        if block.get("type") == "image" and block.get("source_type") == "url":
            url = block.get("url", "")

            # Try to match against storage path in URL (for new messages)
            replaced = False
            for storage_path, signed_url in url_mapping.items():
                if storage_path in url or url == storage_path:
                    modified_block["url"] = signed_url
                    logger.debug(f"[MESSAGE_UTILS] Replaced storage path in image block: {storage_path[:30]}...")
                    replaced = True
                    break

            # If URL already converted, check metadata (for historical messages)
            if not replaced and (url.startswith("http") or url.startswith("data:")):
                metadata_path = extract_storage_path_from_metadata(block)
                if metadata_path and metadata_path in url_mapping:
                    modified_block["url"] = url_mapping[metadata_path]

        # OpenAI style format: {"type": "image_url", "image_url": {"url": "..."}}
        elif block.get("type") == "image_url" and isinstance(block.get("image_url"), dict):
            image_url_obj = block["image_url"].copy()
            url = image_url_obj.get("url", "")

            # Try to match against storage path in URL
            replaced = False
            for storage_path, signed_url in url_mapping.items():
                if storage_path in url or url == storage_path:
                    modified_block["image_url"] = {"url": signed_url}
                    logger.debug(f"[MESSAGE_UTILS] Replaced storage path in image_url block: {storage_path[:30]}...")
                    replaced = True
                    break

            # If URL already converted, check metadata
            if not replaced and (url.startswith("http") or url.startswith("data:")):
                metadata_path = extract_storage_path_from_metadata(block)
                if metadata_path and metadata_path in url_mapping:
                    modified_block["image_url"] = {"url": url_mapping[metadata_path]}

        # All other blocks (including text) are left completely untouched
        modified_blocks.append(modified_block)

    return modified_blocks


async def process_messages_with_signed_urls(
    messages: List[BaseMessage],
    access_token: str,
    langconnect_api_url: str,
    expiry_seconds: int = 1800
) -> List[BaseMessage]:
    """
    Process messages to replace storage paths with temporary signed URLs in image blocks.

    This function scans all messages in the conversation history, finds storage paths
    in IMAGE CONTENT BLOCKS ONLY, generates signed URLs in batch, and replaces the paths.

    It also converts fs_read_image tool results from JSON strings to multimodal content
    blocks so vision-enabled LLMs can actually see the images.

    Local Development Fallback:
    ---------------------------
    When signed URLs use HTTP (local Supabase), they are automatically converted to
    base64 data URLs since Claude's API requires HTTPS. This adds ~1-2MB per image
    to the request but works seamlessly in local development. In production with
    HTTPS storage, URLs remain lightweight.

    Key Points:
    -----------
    - Converts fs_read_image results to multimodal content (text + image)
    - Only processes image content blocks, never text content
    - Production: Uses lightweight HTTPS signed URLs (efficient)
    - Local dev: Converts HTTP URLs to base64 data URLs (seamless)
    - Works with HumanMessage, AIMessage, and ToolMessage

    Usage:
        # In agent graph before model call
        processed_messages = await process_messages_with_signed_urls(
            state["messages"],
            access_token=config["configurable"]["x-supabase-access-token"],
            langconnect_api_url="http://langconnect:8080"
        )

    Args:
        messages: List of messages from state
        access_token: Supabase JWT token
        langconnect_api_url: Base URL of LangConnect API
        expiry_seconds: URL expiry time (default 30 minutes)

    Returns:
        New list of messages with storage paths replaced by signed URLs (or base64 data URLs) in image blocks
    """
    # Step 0: Convert collection_read_image tool results to multimodal content first
    # This also converts HTTP URLs to base64 for local development
    messages = await convert_collection_read_image_to_multimodal(messages)

    # Step 1: Extract all storage paths from image blocks across all messages
    all_storage_paths = []
    for message in messages:
        paths = extract_storage_paths_from_content(message.content)
        all_storage_paths.extend(paths)

    if not all_storage_paths:
        return messages

    unique_paths = set(all_storage_paths)
    logger.debug("[MESSAGE_UTILS] Found %d unique storage paths in image blocks", len(unique_paths))

    # Step 2: Batch generate signed URLs
    url_mapping = await batch_generate_signed_urls(
        all_storage_paths,
        access_token,
        langconnect_api_url,
        expiry_seconds
    )

    if not url_mapping:
        logger.warning("[MESSAGE_UTILS] Failed to generate signed URLs")
        return messages

    # Step 2.5: Convert HTTP URLs to base64 data URLs (local development fallback)
    # Claude's API requires HTTPS URLs, so we convert local HTTP URLs to base64
    http_converted = 0
    http_failed = 0

    for storage_path, signed_url in list(url_mapping.items()):
        if signed_url.startswith("http://"):
            data_url = await convert_http_url_to_base64(signed_url)
            if data_url:
                url_mapping[storage_path] = data_url
                http_converted += 1
            else:
                http_failed += 1

    if http_converted > 0 or http_failed > 0:
        logger.debug(
            "[MESSAGE_UTILS] HTTP to base64 conversion: %d succeeded, %d failed",
            http_converted, http_failed
        )

    # Step 3: Replace storage paths in image blocks only
    processed_messages = []
    for message in messages:
        # Create a new message with replaced content
        modified_content = replace_storage_paths_in_content(
            message.content,
            url_mapping
        )

        # Preserve all message attributes
        if isinstance(message, HumanMessage):
            processed_msg = HumanMessage(
                content=modified_content,
                id=message.id,
                name=message.name,
                additional_kwargs=message.additional_kwargs
            )
        elif isinstance(message, AIMessage):
            processed_msg = AIMessage(
                content=modified_content,
                id=message.id,
                name=message.name,
                additional_kwargs=message.additional_kwargs,
                tool_calls=message.tool_calls if hasattr(message, 'tool_calls') else []
            )
        elif isinstance(message, ToolMessage):
            processed_msg = ToolMessage(
                content=modified_content,
                id=message.id,
                name=message.name,
                tool_call_id=message.tool_call_id,
                additional_kwargs=message.additional_kwargs
            )
        else:
            # Fallback for other message types
            processed_msg = message.__class__(
                content=modified_content,
                **{k: v for k, v in message.dict().items() if k != 'content'}
            )

        processed_messages.append(processed_msg)

    return processed_messages


def create_image_preprocessor(
    langconnect_api_url: str,
    expiry_seconds: int = 1800
):
    """
    Create a pre-model hook that processes messages with storage paths.

    This factory function returns a hook compatible with LangGraph's pre_model_hook
    parameter in create_react_agent. The hook automatically converts storage paths
    in image content blocks to signed URLs before every model invocation.

    Usage:
        # In agent graph.py
        from agent_platform.utils.message_utils import create_image_preprocessor

        image_hook = create_image_preprocessor("http://langconnect:8080")

        agent = create_react_agent(
            model=model,
            tools=tools,
            pre_model_hook=image_hook,  # Apply before every model call
            ...
        )

    Args:
        langconnect_api_url: Base URL of LangConnect API
        expiry_seconds: URL expiry time (default 30 minutes)

    Returns:
        Async hook function compatible with pre_model_hook
    """
    async def image_preprocessor_hook(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-model hook that replaces storage paths with signed URLs in image blocks.

        This hook is called before every model invocation and processes the
        messages to replace storage paths with temporary signed URLs.
        """
        # Extract access token from config
        access_token = (
            config.get("configurable", {}).get("x-supabase-access-token") or
            config.get("metadata", {}).get("supabaseAccessToken")
        )

        if not access_token:
            logger.debug("[IMAGE_HOOK] No access token found in config, skipping image processing")
            return state

        # Process messages
        # Check for llm_input_messages first (set by trimming hook), fall back to messages
        messages_key = "llm_input_messages" if "llm_input_messages" in state else "messages"
        messages = state.get(messages_key, [])
        if not messages:
            return state

        try:
            processed_messages = await process_messages_with_signed_urls(
                messages,
                access_token,
                langconnect_api_url,
                expiry_seconds
            )

            # Return modified state with processed messages in the same key we read from
            return {**state, messages_key: processed_messages}

        except Exception as e:
            logger.warning("[IMAGE_HOOK] Error processing messages: %s", str(e)[:100])
            return state

    return image_preprocessor_hook
