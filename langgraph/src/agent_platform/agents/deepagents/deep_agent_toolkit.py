from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from typing import Annotated, Union
from langgraph.prebuilt import InjectedState

try:
    from .deep_agent_toolkit_descriptions import (
        WRITE_TODOS_DESCRIPTION,
        EDIT_DESCRIPTION,
        READ_FILE_TOOL_DESCRIPTION,
    )
    from .state import Todo, DeepAgentState
except ImportError:
    from agent_platform.agents.deepagents.deep_agent_toolkit_descriptions import (
        WRITE_TODOS_DESCRIPTION,
        EDIT_DESCRIPTION,
        READ_FILE_TOOL_DESCRIPTION,
    )
    from agent_platform.agents.deepagents.state import Todo, DeepAgentState


@tool(description=WRITE_TODOS_DESCRIPTION)
def write_todos(
    todos: list[Todo], tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    return Command(
        update={
            "todos": todos,
            "messages": [
                ToolMessage(f"Updated todo list to {todos}", tool_call_id=tool_call_id)
            ],
        }
    )


def ls(state: Annotated[DeepAgentState, InjectedState]) -> dict:
    """List all files with metadata in structured format.

    For images, only return minimal fields: name (URL), url, and source.
    For non-images, return filename and source.
    """
    files = state.get("files", {})
    if not files:
        return {
            "total_files": 0,
            "files": [],
            "summary": "No files in the system."
        }
    
    structured_files = []
    file_type_counts = {}
    
    for filename, file_entry in files.items():
        metadata = file_entry.get("metadata", {})
        file_type = metadata.get("type", "file")
        source = metadata.get("source", "unknown")
        
        # Count file types
        file_type_counts[file_type] = file_type_counts.get(file_type, 0) + 1
        
        # Create structured file entry (minimal for images)
        if file_type == "image":
            url = metadata.get("url") or metadata.get("gcp_url") or metadata.get("gcp_path") or filename
            file_info = {
                "type": file_type,
                "source": source,
                "name": url,
                "url": url,
            }
        else:
            file_info = {
                "filename": filename,
                "type": file_type,
                "source": source,
            }
        
        structured_files.append(file_info)
    
    # Sort files by type (images first) then by a stable label (url/name/filename)
    def _sort_label(x):
        return x.get("filename") or x.get("url") or x.get("name") or ""
    structured_files.sort(key=lambda x: (x.get("type") != "image", _sort_label(x)))
    
    return {
        "total_files": len(files),
        "files": structured_files,
        "file_type_counts": file_type_counts,
        "summary": f"Found {len(files)} file(s): {', '.join([f'{count} {ftype}(s)' for ftype, count in file_type_counts.items()])}"
    }


@tool(description=READ_FILE_TOOL_DESCRIPTION)
def read_file(
    file_path: str,
    state: Annotated[DeepAgentState, InjectedState],
    offset: int = 0,
    limit: int = 2000,
) -> str:
    """Read file."""
    mock_filesystem = state.get("files", {})
    if file_path not in mock_filesystem:
        return f"Error: File '{file_path}' not found"

    # Get file entry
    file_entry = mock_filesystem[file_path]
    content = file_entry["content"]

    # Handle empty file
    if not content or content.strip() == "":
        return "System reminder: File exists but has empty contents"

    # Split content into lines
    lines = content.splitlines()

    # Apply line offset and limit
    start_idx = offset
    end_idx = min(start_idx + limit, len(lines))

    # Handle case where offset is beyond file length
    if start_idx >= len(lines):
        return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"

    # Format output with line numbers (cat -n format)
    result_lines = []
    for i in range(start_idx, end_idx):
        line_content = lines[i]

        # Truncate lines longer than 2000 characters
        if len(line_content) > 2000:
            line_content = line_content[:2000]

        # Line numbers start at 1, so add 1 to the index
        line_number = i + 1
        result_lines.append(f"{line_number:6d}\t{line_content}")

    return "\n".join(result_lines)


def write_file(
    file_path: str,
    content: str,
    state: Annotated[DeepAgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Write to a file."""
    files = state.get("files", {})
    files[file_path] = {
        "content": content,
        "metadata": {
            "type": "file",
            "source": "ai_generated"
        }
    }
    return Command(
        update={
            "files": files,
            "messages": [
                ToolMessage(f"Updated file {file_path}", tool_call_id=tool_call_id)
            ],
        }
    )


@tool(description=EDIT_DESCRIPTION)
def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    state: Annotated[DeepAgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    replace_all: bool = False,
) -> Union[Command, str]:
    """Write to a file."""
    mock_filesystem = state.get("files", {})
    # Check if file exists in mock filesystem
    if file_path not in mock_filesystem:
        return f"Error: File '{file_path}' not found"

    # Get current file entry and content
    file_entry = mock_filesystem[file_path]
    content = file_entry["content"]

    # Check if old_string exists in the file
    if old_string not in content:
        return f"Error: String not found in file: '{old_string}'"

    # If not replace_all, check for uniqueness
    if not replace_all:
        occurrences = content.count(old_string)
        if occurrences > 1:
            return f"Error: String '{old_string}' appears {occurrences} times in file. Use replace_all=True to replace all instances, or provide a more specific string with surrounding context."
        elif occurrences == 0:
            return f"Error: String not found in file: '{old_string}'"

    # Perform the replacement
    if replace_all:
        new_content = content.replace(old_string, new_string)
        replacement_count = content.count(old_string)
        result_msg = f"Successfully replaced {replacement_count} instance(s) of the string in '{file_path}'"
    else:
        new_content = content.replace(
            old_string, new_string, 1
        )  # Replace only first occurrence
        result_msg = f"Successfully replaced string in '{file_path}'"

    # Update the mock filesystem - preserve metadata
    mock_filesystem[file_path] = {
        "content": new_content,
        "metadata": file_entry.get("metadata", {})
    }
    return Command(
        update={
            "files": mock_filesystem,
            "messages": [ToolMessage(result_msg, tool_call_id=tool_call_id)],
        }
    )