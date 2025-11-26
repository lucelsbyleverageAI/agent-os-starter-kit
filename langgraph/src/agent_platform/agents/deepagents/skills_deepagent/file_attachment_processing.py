"""File attachment processing for Skills DeepAgent - writes to sandbox.

This is a modified version of deepagents/file_attachment_processing.py that:
1. Writes uploaded files to /sandbox/user_uploads/ instead of state.files
2. Uses SkillsDeepAgentState (no files field)
3. Requires a sandbox to be initialized for the thread
"""

import re
from typing import Annotated, Optional
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from agent_platform.sentry import get_logger

try:
    from .state import SkillsDeepAgentState
    from .sandbox_tools import get_sandbox
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.state import SkillsDeepAgentState
    from agent_platform.agents.deepagents.skills_deepagent.sandbox_tools import get_sandbox

logger = get_logger(__name__)


def extract_file_attachments_to_sandbox(
    state: Annotated[SkillsDeepAgentState, InjectedState],
    thread_id: str,
) -> Command:
    """Extract file attachments from messages and write to sandbox.

    Files are written to /sandbox/user_uploads/<filename>.md

    Returns Command with empty update (files are in sandbox, not state).
    """
    messages = state.get("messages", [])
    if not messages:
        return Command(update={})

    latest_message = messages[-1]
    if not isinstance(latest_message, HumanMessage):
        return Command(update={})

    # Extract file attachments from the message content
    message_content = None

    # Handle both string and list content formats
    if isinstance(latest_message.content, str):
        message_content = latest_message.content
    elif isinstance(latest_message.content, list):
        # Collect ALL text blocks that contain UserUploadedAttachment
        attachment_texts = []
        for content_item in latest_message.content:
            if isinstance(content_item, dict) and content_item.get('type') == 'text':
                text = content_item.get('text', '')
                if '<UserUploadedAttachment>' in text:
                    attachment_texts.append(text)
        # Concatenate all attachment texts
        if attachment_texts:
            message_content = '\n'.join(attachment_texts)

    if not message_content or '<UserUploadedAttachment>' not in message_content:
        logger.debug("[SKILLS_FILE_ATTACH] No file attachments found in message")
        return Command(update={})

    # Extract all UserUploadedAttachment blocks using regex
    attachment_pattern = r'<UserUploadedAttachment>(.*?)</UserUploadedAttachment>'
    attachment_matches = re.finditer(attachment_pattern, message_content, re.DOTALL)

    attachments_found = []
    for match in attachment_matches:
        attachment_content = match.group(1)

        # Extract FileType, FileName, and Content
        file_type_match = re.search(r'<FileType>(.*?)</FileType>', attachment_content, re.DOTALL)
        file_name_match = re.search(r'<FileName>(.*?)</FileName>', attachment_content, re.DOTALL)
        content_match = re.search(r'<Content>(.*?)</Content>', attachment_content, re.DOTALL)

        if file_type_match and file_name_match and content_match:
            file_type = file_type_match.group(1).strip()
            file_name = file_name_match.group(1).strip()
            file_content = content_match.group(1).strip()

            attachments_found.append({
                'file_type': file_type,
                'file_name': file_name,
                'content': file_content,
            })
            logger.info("[SKILLS_FILE_ATTACH] Found attachment: %s (type: %s)", file_name, file_type)

    if not attachments_found:
        logger.debug("[SKILLS_FILE_ATTACH] No valid attachments found after parsing")
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

    # Write each attachment to sandbox
    for attachment in attachments_found:
        original_file_name = attachment['file_name']
        content = attachment['content']

        # Convert to markdown filename (append .md to preserve original name context)
        markdown_file_name = f"{original_file_name}.md"
        sandbox_path = f"/sandbox/user_uploads/{markdown_file_name}"

        try:
            sandbox.files.write(sandbox_path, content.encode('utf-8'))
            logger.info("[SKILLS_FILE_ATTACH] Wrote %s to %s", original_file_name, sandbox_path)
        except Exception as e:
            logger.error("[SKILLS_FILE_ATTACH] Failed to write %s: %s", original_file_name, str(e))

    logger.info("[SKILLS_FILE_ATTACH] Extracted %d file attachment(s) to sandbox", len(attachments_found))

    # Return empty update - files are in sandbox, not state
    return Command(update={})


def create_file_attachment_node(thread_id: str):
    """Create a file attachment processing node bound to a specific thread.

    Returns a function that can be used as a LangGraph node.
    """
    def file_attachment_node(state: SkillsDeepAgentState) -> Command:
        return extract_file_attachments_to_sandbox(state, thread_id)

    return file_attachment_node
