"""State schema for Skills DeepAgent - sandbox-only, no state filesystem.

Unlike the base DeepAgentState, this state does NOT include a `files` field.
All file operations happen in the E2B sandbox via the execute_in_sandbox tool.
"""

from langgraph.prebuilt.chat_agent_executor import AgentState
from typing import NotRequired, Literal, List, Annotated
from typing_extensions import TypedDict


class Todo(TypedDict):
    """Todo item for task tracking."""
    content: str
    status: Literal["pending", "in_progress", "completed"]


class PublishedFile(TypedDict):
    """A file published by the agent for user download/preview.

    When an agent creates a file and wants to share it with the user,
    it calls publish_file_to_user which uploads the file to Supabase Storage
    and adds this record to published_files.
    """
    display_name: str           # User-friendly name (e.g., "Quarterly Report")
    description: str            # Brief description of the file
    filename: str               # Original filename (e.g., "report.docx")
    file_type: str              # File extension (e.g., ".docx")
    mime_type: str              # MIME type (e.g., "application/vnd.openxmlformats...")
    file_size: int              # Size in bytes
    storage_path: str           # Supabase storage path (e.g., "user_id/thread_id/report.docx")
    sandbox_path: str           # Original sandbox path (e.g., "/sandbox/outputs/report.docx")
    published_at: str           # ISO timestamp


def published_files_reducer(
    existing: List[PublishedFile] | None,
    new: List[PublishedFile] | None
) -> List[PublishedFile]:
    """Reducer for published_files that handles updates by display_name.

    If a file with the same display_name already exists, it is replaced.
    This allows agents to update/revise files without creating duplicates.
    """
    if existing is None:
        existing = []
    if new is None:
        return existing

    result = list(existing)

    for new_file in new:
        # Check if file with same display_name exists
        found_idx = None
        for i, existing_file in enumerate(result):
            if existing_file.get("display_name") == new_file.get("display_name"):
                found_idx = i
                break

        if found_idx is not None:
            # Update existing file
            result[found_idx] = new_file
        else:
            # Add new file
            result.append(new_file)

    return result


class SkillsDeepAgentState(AgentState):
    """State for Skills DeepAgent.

    Unlike base DeepAgentState, this does NOT include a `files` field.
    All file operations happen in the E2B sandbox.

    Fields:
        messages: Conversation history (inherited from AgentState)
        todos: Task tracking list
        published_files: Files published by the agent for user download
    """
    todos: NotRequired[list[Todo]]
    published_files: Annotated[NotRequired[List[PublishedFile]], published_files_reducer]
