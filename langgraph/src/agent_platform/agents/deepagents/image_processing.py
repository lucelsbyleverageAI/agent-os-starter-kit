"""Parallel image processing nodes for extracting and registering user uploaded images."""

from typing import Annotated, Any, Dict, List, Optional, NotRequired
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.types import Command, Send
from langgraph.prebuilt import InjectedState
from typing_extensions import TypedDict
from agent_platform.sentry import get_logger
logger = get_logger(__name__)

try:
    from .state import DeepAgentState, FileEntry, file_reducer
except ImportError:
    from agent_platform.agents.deepagents.state import DeepAgentState, FileEntry, file_reducer


# Note: We now use DeepAgentState for all nodes to avoid schema conflicts
# Image-specific data is passed through the 'current_image' key in the state


# Tool for the vision model to generate image metadata
@tool
def generate_image_metadata(name: str, description: str) -> str:
    """Generate metadata for an uploaded image.
    
    Args:
        name: A short descriptive name for the image (max 5 words)
        description: A 2-3 sentence description of what's in the image
    """
    return f"Generated metadata - Name: {name}, Description: {description}"


def dispatch_image_processing(
    state: Annotated[DeepAgentState, InjectedState]
) -> Command:
    """Dispatcher node that identifies images and creates parallel Send commands.
    
    This node:
    1. Identifies all images in the latest user message
    2. Creates Send commands for parallel processing of each image
    3. Returns Command with Send list for parallel execution
    """
    messages = state.get("messages", [])
    if not messages:
        return Command(update={})
    
    # Get the latest message (should be user message)
    latest_message = messages[-1]
    if not isinstance(latest_message, HumanMessage):
        return Command(update={})
    
    # Extract images from the message content
    images_found = []
    if hasattr(latest_message, 'content') and isinstance(latest_message.content, list):
        for content_item in latest_message.content:
            if isinstance(content_item, dict) and content_item.get('type') == 'image_url':
                image_url_dict = content_item.get('image_url', {})
                image_url = image_url_dict.get('url', '')
                
                # Extract storage path from various sources (Supabase storage)
                storage_path = None
                bucket_name = None

                # Check attachments for storagePath (new format)
                if (hasattr(latest_message, 'additional_kwargs') and
                    isinstance(latest_message.additional_kwargs, dict) and
                    'attachments' in latest_message.additional_kwargs):

                    attachments = latest_message.additional_kwargs['attachments']
                    if isinstance(attachments, list):
                        for attachment in attachments:
                            if (isinstance(attachment, dict) and
                                attachment.get('type') == 'image'):
                                # Support both new storagePath and legacy gcsPath
                                storage_path = attachment.get('storagePath') or attachment.get('gcsPath')
                                bucket_name = attachment.get('bucket')
                                if storage_path:
                                    # Remove storage:// prefix if present
                                    if storage_path.startswith('storage://'):
                                        parts = storage_path.replace('storage://', '').split('/', 1)
                                        if len(parts) == 2:
                                            bucket_name = parts[0]
                                            storage_path = parts[1]
                                    break

                # Check metadata for storage_path (try both new and legacy keys)
                if not storage_path:
                    metadata = content_item.get('metadata', {})
                    if isinstance(metadata, dict):
                        storage_path = metadata.get('storage_path') or metadata.get('gcp_path')
                        bucket_name = metadata.get('bucket')

                # Extract from Supabase signed URL if no storage_path found
                if not storage_path:
                    import os
                    supabase_url = os.getenv("SUPABASE_PUBLIC_URL", os.getenv("SUPABASE_URL", ""))
                    if supabase_url and supabase_url in image_url:
                        # Parse Supabase storage URL: http://localhost:8000/storage/v1/object/sign/bucket-name/path...
                        if '/storage/v1/object/' in image_url:
                            # Extract bucket and path from URL
                            parts = image_url.split('/storage/v1/object/', 1)
                            if len(parts) > 1:
                                object_path = parts[1].split('/', 1)
                                if len(object_path) > 1:
                                    # Skip 'sign' or 'public' prefix
                                    if object_path[0] in ['sign', 'public']:
                                        remaining = object_path[1].split('/', 1)
                                        if len(remaining) > 1:
                                            bucket_name = remaining[0]
                                            storage_path = remaining[1].split('?')[0]  # Remove query params

                if storage_path and image_url:
                    images_found.append({
                        'storage_path': storage_path,
                        'bucket': bucket_name or 'chat-uploads',  # Default to chat-uploads bucket
                        'image_url': image_url
                    })
    
    if not images_found:
        logger.info("[IMAGE_DISPATCH] no_images_found=true")
        return Command(goto="continue_after_image_processing")
    
    # Create Send commands for parallel processing of each image
    send_commands = []
    for i, image_info in enumerate(images_found):
        # Create a state update that includes the image-specific data
        image_state = {
            **state,  # Include all existing state
            'current_image': {
                'storage_path': image_info['storage_path'],
                'bucket': image_info['bucket'],
                'image_url': image_info['image_url'],
                'image_index': i
            }
        }
        send_commands.append(
            Send("process_single_image", image_state)
        )
    
    logger.info("[IMAGE_DISPATCH] dispatching_images count=%s", len(send_commands))
    return Command(goto=send_commands)


async def process_single_image(
    state: Annotated[DeepAgentState, InjectedState]
) -> Command:
    """Process a single image in parallel.
    
    This node:
    1. Takes a single image's info from the dispatched state
    2. Uses GPT-4o-mini to generate metadata for the image
    3. Returns file system update for this specific image
    """
    current_image = state.get('current_image', {})
    storage_path = current_image.get('storage_path')
    bucket = current_image.get('bucket', 'chat-uploads')
    image_url = current_image.get('image_url')
    image_index = current_image.get('image_index', 0)

    if not storage_path or not image_url:
        logger.error("[IMAGE_PROCESS] missing_image_data index=%s", image_index)
        return Command(
            update={
                "files": {}  # Return empty update if no image data
            },
            goto="continue_after_image_processing"
        )

    logger.debug("[IMAGE_PROCESS] processing_image index=%s storage_path=%s bucket=%s", image_index, storage_path, bucket)
    
    # Set up vision model for metadata generation
    vision_model = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    ).bind_tools([generate_image_metadata])
    
    # Create a message with the image for the vision model
    vision_message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": "For this image, create a name and description and output using the tool provided. You must use the generate_image_metadata tool. The name should be a short descriptive name (max 5 words) and the description should be 2-3 sentences describing what's in the image."
            },
            {
                "type": "image_url",
                "image_url": {"url": image_url}
            }
        ]
    )
    
    try:
        # Get metadata from vision model
        response = await vision_model.ainvoke([vision_message])
        
        # Extract tool call results
        if isinstance(response, AIMessage) and response.tool_calls:
            tool_call = response.tool_calls[0]
            name = tool_call['args'].get('name', 'Uploaded Image')
            description = tool_call['args'].get('description', 'User uploaded image')
            
            logger.debug("[IMAGE_PROCESS] metadata_generated index=%s", image_index)
        else:
            name = 'Uploaded Image'
            description = 'User uploaded image'
            logger.info("[IMAGE_PROCESS] no_tool_calls_using_fallback index=%s", image_index)
            
    except Exception as e:
        name = 'Uploaded Image'
        description = f"User uploaded image (metadata generation failed: {str(e)})"
        logger.exception("[IMAGE_PROCESS] metadata_generation_failed index=%s", image_index)
    
    # Construct Supabase storage reference
    import os
    supabase_url = os.getenv("SUPABASE_PUBLIC_URL", os.getenv("SUPABASE_URL", ""))

    # Create storage:// URI for consistent reference
    storage_uri = f"storage://{bucket}/{storage_path}"

    # Make the key unique by adding image index to handle duplicate URLs
    unique_key = f"{storage_uri}#image_{image_index}"

    # Create file entry for this image
    file_entry = {
        unique_key: {
            "content": description,  # Use description as content
            "metadata": {
                "type": "image",
                "source": "user_upload",
                # Store Supabase storage references
                "storage_uri": storage_uri,
                "storage_path": storage_path,
                "bucket": bucket,
                # Name should be the storage URI
                "name": storage_uri,
                "url": image_url,  # Keep the signed URL for rendering
                "description": description
            }
        }
    }

    logger.info("[IMAGE_PROCESS] completed index=%s storage_uri=%s", image_index, storage_uri)
    
    # Return file system update for this image (reducer will merge with others)
    return Command(
        update={
            "files": file_entry
        },
        goto="continue_after_image_processing"
    )


def continue_after_image_processing(
    state: Annotated[DeepAgentState, InjectedState]
) -> Command:
    """Continuation node that runs after all image processing is complete.
    
    This node serves as a fan-in point for all parallel image processing nodes
    and provides a single exit point to continue the workflow.
    """
    files = state.get("files", {})
    all_file_keys = list(files.keys()) if files else []
    image_files = [f for f in files.values() if f.get("metadata", {}).get("source") == "user_upload"] if files else []
    image_count = len(image_files)
    
    logger.info("[IMAGE_CONTINUE] fan_in_complete total_files=%s user_uploaded_images=%s", len(all_file_keys), image_count)
    
    if image_count > 0:
        logger.info("[IMAGE_CONTINUE] images_registered count=%s", image_count)
    else:
        logger.info("[IMAGE_CONTINUE] no_images_after_processing=true")
    
    # Just pass through - no updates needed
    return Command(update={})


def extract_user_uploaded_images_sync(
    state: Annotated[DeepAgentState, InjectedState]
) -> Command:
    """Synchronous wrapper for extract_user_uploaded_images."""
    import asyncio
    
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, we need to create a new task
            # This is a fallback - in practice, the async version should be used
            return Command(update={})
        else:
            return loop.run_until_complete(extract_user_uploaded_images(state))
    except RuntimeError:
        # No event loop exists, create one
        return asyncio.run(extract_user_uploaded_images(state))
