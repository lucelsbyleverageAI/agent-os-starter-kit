"""File attachment processing node for extracting user uploaded files from XML tags."""

import re
from typing import Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from agent_platform.sentry import get_logger

logger = get_logger(__name__)

try:
    from .state import DeepAgentState, FileEntry
except ImportError:
    from agent_platform.agents.deepagents.state import DeepAgentState, FileEntry


def extract_file_attachments(
    state: Annotated[DeepAgentState, InjectedState]
) -> Command:
    """Extract file attachments from XML tags in user messages and save as markdown.

    This node:
    1. Identifies <UserUploadedAttachment> XML tags in the latest user message
    2. Extracts FileType, FileName, and Content from each attachment
    3. Saves them to the agent's file system (state.files) as markdown files
    4. Modifies the message to inform the agent about the uploaded files

    The XML format expected:
    <UserUploadedAttachment>
    <FileType>application/vnd.openxmlformats-officedocument.spreadsheetml.sheet</FileType>
    <FileName>example.xlsx</FileName>
    <Content>
    ... markdown content ...
    </Content>
    </UserUploadedAttachment>

    Files are stored with .md extension (e.g., example.xlsx -> example.xlsx.md)
    """
    messages = state.get("messages", [])
    if not messages:
        return Command(update={})

    # Get the latest message (should be user message)
    latest_message = messages[-1]
    if not isinstance(latest_message, HumanMessage):
        return Command(update={})

    # Extract file attachments from the message content
    attachments_found = []
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
        logger.debug("[FILE_ATTACH] No file attachments found in message")
        return Command(update={})

    # Extract all UserUploadedAttachment blocks using regex
    attachment_pattern = r'<UserUploadedAttachment>(.*?)</UserUploadedAttachment>'
    attachment_matches = re.finditer(attachment_pattern, message_content, re.DOTALL)

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
            logger.info("[FILE_ATTACH] Found attachment: %s (type: %s)", file_name, file_type)

    if not attachments_found:
        logger.debug("[FILE_ATTACH] No valid attachments found after parsing")
        return Command(update={})

    # Create file entries for each attachment
    file_updates = {}

    for attachment in attachments_found:
        original_file_name = attachment['file_name']
        original_file_type = attachment['file_type']
        content = attachment['content']

        # Convert to markdown filename (append .md to preserve original name context)
        markdown_file_name = f"{original_file_name}.md"

        # Create file entry
        file_entry: FileEntry = {
            "content": content,
            "metadata": {
                "type": "document",
                "source": "user_upload",
                "mime_type": "text/markdown",
                "filename": markdown_file_name,
                "original_filename": original_file_name,
                "original_mime_type": original_file_type,
            }
        }

        file_updates[markdown_file_name] = file_entry

    logger.info("[FILE_ATTACH] Extracted %d file attachment(s) as markdown", len(attachments_found))

    # Return updates for files only (system note will be injected at model call time)
    return Command(
        update={
            "files": file_updates,
        }
    )
