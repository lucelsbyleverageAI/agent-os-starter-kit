"""
Message processing utilities for LangGraph agents.

This module provides utilities for:
1. Cleaning orphaned tool calls from message history
2. Converting storage paths to signed URLs in image content blocks
3. Local dev fallback: Converting HTTP URLs to base64 data URLs for Claude API
4. Converting fs_read_image tool results to multimodal content blocks
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

    logger.debug("[CLEAN_MESSAGES] start count=%s", len(messages))

    # Step 1: Identify all tool call IDs and their states
    tool_call_ids_made = set()  # Tool calls made by AI messages
    tool_call_ids_responded = set()  # Tool calls that got responses

    # Step 2: Scan messages to build the state
    for i, message in enumerate(messages):
        if isinstance(message, AIMessage) and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_call_ids_made.add(tool_call["id"])
            logger.debug("[CLEAN_MESSAGES] ai_message_with_tool_calls index=%s count=%s", i, len(message.tool_calls))
        elif isinstance(message, ToolMessage):
            tool_call_ids_responded.add(message.tool_call_id)
            logger.debug("[CLEAN_MESSAGES] tool_response index=%s call_id=%s", i, message.tool_call_id)

    # Step 3: Find orphaned tool call IDs
    orphaned_tool_call_ids = tool_call_ids_made - tool_call_ids_responded
    orphaned_tool_message_ids = tool_call_ids_responded - tool_call_ids_made

    all_orphaned_ids = orphaned_tool_call_ids | orphaned_tool_message_ids


    # Step 4: Use LangChain's filter_messages to clean up if needed
    if all_orphaned_ids:
        logger.debug("[CLEAN_MESSAGES] filtering_orphans count=%s", len(all_orphaned_ids))
        cleaned_messages = filter_messages(
            messages,
            exclude_tool_calls=list(all_orphaned_ids)
        )
        logger.debug("[CLEAN_MESSAGES] filtered from=%s to=%s", len(messages), len(cleaned_messages))
        return cleaned_messages

    logger.debug("[CLEAN_MESSAGES] no_orphans=true")
    return messages


# ==================== fs_read_image Tool Result Processing ====================

async def convert_fs_read_image_to_multimodal(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Convert fs_read_image tool results from JSON strings to multimodal content blocks.

    The fs_read_image tool returns a JSON string containing image description and signed URL.
    This function detects those ToolMessages and converts them to multimodal content with:
    - Text description
    - Image content block with the signed URL (converted to base64 if HTTP for local dev)

    This allows vision-enabled LLMs to actually see the images, not just read descriptions.

    Args:
        messages: List of BaseMessage objects to process

    Returns:
        List of BaseMessage objects with fs_read_image results converted to multimodal content

    Example:
        >>> # ToolMessage with JSON content becomes multimodal
        >>> before = ToolMessage(
        ...     content='{"description": "A cat", "metadata": {"signed_url": "https://..."}}',
        ...     name="fs_read_image",
        ...     tool_call_id="call_123"
        ... )
        >>> after = await convert_fs_read_image_to_multimodal([before])
        >>> # Now content is: [
        >>> #   {"type": "text", "text": "A cat"},
        >>> #   {"type": "image_url", "image_url": {"url": "https://..."}}
        >>> # ]
    """
    if not messages:
        return messages

    processed_messages = []
    for message in messages:
        # Only process ToolMessages from fs_read_image
        if not isinstance(message, ToolMessage):
            processed_messages.append(message)
            continue

        # Check if this is from fs_read_image tool
        if message.name != "fs_read_image":
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
                logger.warning(f"[FS_READ_IMAGE] No signed_url found in tool result")
                processed_messages.append(message)
                continue

            # Fix localhost URL issue (kong:8000 -> localhost:8000)
            if "kong:8000" in signed_url:
                signed_url = signed_url.replace("kong:8000", "localhost:8000")
                logger.debug(f"[FS_READ_IMAGE] Fixed kong URL to localhost")

            # Convert HTTP URLs to base64 for local development (Claude requires HTTPS)
            if signed_url.startswith("http://"):
                logger.info(f"[FS_READ_IMAGE] Converting HTTP URL to base64 for local dev")
                data_url = await convert_http_url_to_base64(signed_url)
                if data_url:
                    signed_url = data_url
                    logger.info(f"[FS_READ_IMAGE] Successfully converted to base64 data URL")
                else:
                    logger.warning(f"[FS_READ_IMAGE] Failed to convert HTTP URL to base64, will fail with Claude API")

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

            logger.info(f"[FS_READ_IMAGE] Converted tool result to multimodal content: {name}")
            processed_messages.append(processed_msg)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"[FS_READ_IMAGE] Failed to parse tool result as JSON: {e}")
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
        logger.warning(f"[IMAGE_FORMAT] Unknown magic bytes: {image_data[:8].hex()}, defaulting to PNG")
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

            logger.info(
                f"[MESSAGE_UTILS] Converted HTTP URL to base64 data URL: "
                f"{len(image_data)} bytes, detected format: {content_type}"
            )

            return data_url

    except Exception as e:
        logger.exception(f"[MESSAGE_UTILS] Failed to convert HTTP URL to base64: {url[:50]}...")
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
        # Call LangConnect batch URL generation endpoint
        logger.info(
            f"[MESSAGE_UTILS] Requesting signed URLs for {len(unique_paths)} paths: "
            f"{unique_paths}"
        )

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

            logger.debug(
                f"[MESSAGE_UTILS] Batch signed URLs API response: {data}"
            )

            # Returns: {"signed_urls": {"path1": "url1", "path2": "url2", ...}}
            signed_urls = data.get("signed_urls", {})

            if not signed_urls:
                logger.warning(
                    f"[MESSAGE_UTILS] API returned no signed URLs! "
                    f"Response data: {data}"
                )

            return signed_urls

    except Exception as e:
        logger.exception(f"[MESSAGE_UTILS] Failed to batch generate signed URLs: {e}")
        return {}


def extract_storage_paths_from_content(content: Any) -> List[str]:
    """
    Extract storage paths from message content.

    IMPORTANT: Only extracts from IMAGE CONTENT BLOCKS, not from text blocks.
    This ensures we only replace URLs where the LLM needs to actually view the image.

    Supported Formats:
    ------------------
    1. LangChain standard: {"type": "image", "source_type": "url", "url": "..."}
    2. OpenAI style: {"type": "image_url", "image_url": {"url": "..."}}

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
            if url and not url.startswith("http"):
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

        # OpenAI style format: {"type": "image_url", "image_url": {"url": "..."}}
        elif block.get("type") == "image_url":
            image_url_obj = block.get("image_url", {})
            if isinstance(image_url_obj, dict):
                url = image_url_obj.get("url", "")
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

    return paths


def replace_storage_paths_in_content(content: Any, url_mapping: Dict[str, str]) -> Any:
    """
    Replace storage paths with signed URLs in message content.

    IMPORTANT: Only replaces in IMAGE CONTENT BLOCKS, not in text blocks.
    Text references to storage paths are left completely untouched.

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

        modified_block = block.copy()

        # LangChain standard format: {"type": "image", "source_type": "url", "url": "..."}
        if block.get("type") == "image" and block.get("source_type") == "url":
            url = block.get("url", "")
            # Replace storage path with signed URL
            for storage_path, signed_url in url_mapping.items():
                if storage_path in url or url == storage_path:
                    modified_block["url"] = signed_url
                    logger.debug(f"[MESSAGE_UTILS] Replaced storage path in image block: {storage_path[:30]}...")
                    break

        # OpenAI style format: {"type": "image_url", "image_url": {"url": "..."}}
        elif block.get("type") == "image_url" and isinstance(block.get("image_url"), dict):
            image_url_obj = block["image_url"].copy()
            url = image_url_obj.get("url", "")
            # Replace storage path with signed URL
            for storage_path, signed_url in url_mapping.items():
                if storage_path in url or url == storage_path:
                    modified_block["image_url"] = {"url": signed_url}
                    logger.debug(f"[MESSAGE_UTILS] Replaced storage path in image_url block: {storage_path[:30]}...")
                    break

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
    # Step 0: Convert fs_read_image tool results to multimodal content first
    # This also converts HTTP URLs to base64 for local development
    messages = await convert_fs_read_image_to_multimodal(messages)

    # Step 1: Extract all storage paths from image blocks across all messages
    all_storage_paths = []
    for message in messages:
        content = message.content
        paths = extract_storage_paths_from_content(content)
        if paths:
            logger.info(
                f"[MESSAGE_UTILS] Extracted {len(paths)} paths from message: {paths}"
            )
        all_storage_paths.extend(paths)

    if not all_storage_paths:
        # No storage paths found in image blocks
        return messages

    logger.info(
        f"[MESSAGE_UTILS] Found {len(set(all_storage_paths))} unique storage paths "
        f"in image blocks across {len(messages)} messages: {list(set(all_storage_paths))}"
    )

    # Step 2: Batch generate signed URLs
    url_mapping = await batch_generate_signed_urls(
        all_storage_paths,
        access_token,
        langconnect_api_url,
        expiry_seconds
    )

    if not url_mapping:
        logger.warning("[MESSAGE_UTILS] Failed to generate any signed URLs")
        return messages

    logger.info(
        f"[MESSAGE_UTILS] Generated {len(url_mapping)} signed URLs "
        f"(expiry: {expiry_seconds}s)"
    )

    # Step 2.5: Convert HTTP URLs to base64 data URLs (local development fallback)
    # Claude's API requires HTTPS URLs, so we convert local HTTP URLs to base64
    http_conversions = []
    for storage_path, signed_url in list(url_mapping.items()):
        if signed_url.startswith("http://"):
            logger.info(
                f"[MESSAGE_UTILS] Converting HTTP URL to base64 for local dev: "
                f"{signed_url[:60]}..."
            )
            data_url = await convert_http_url_to_base64(signed_url)
            if data_url:
                url_mapping[storage_path] = data_url
                http_conversions.append(storage_path)
            else:
                logger.warning(
                    f"[MESSAGE_UTILS] Failed to convert HTTP URL, will try anyway: "
                    f"{signed_url[:60]}..."
                )

    if http_conversions:
        logger.info(
            f"[MESSAGE_UTILS] Converted {len(http_conversions)} HTTP URLs to base64 data URLs "
            f"(local development fallback)"
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
            logger.warning("[IMAGE_HOOK] No access token found in config, skipping image processing")
            return state

        # Process messages
        messages = state.get("messages", [])
        if not messages:
            return state

        try:
            processed_messages = await process_messages_with_signed_urls(
                messages,
                access_token,
                langconnect_api_url,
                expiry_seconds
            )

            # Return modified state
            return {**state, "messages": processed_messages}

        except Exception as e:
            logger.exception(f"[IMAGE_HOOK] Error processing messages: {e}")
            # On error, return original state
            return state

    return image_preprocessor_hook
