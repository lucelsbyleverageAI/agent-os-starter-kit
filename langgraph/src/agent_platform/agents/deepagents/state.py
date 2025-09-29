from langgraph.prebuilt.chat_agent_executor import AgentState
from typing import NotRequired, Annotated, Any, Dict
from typing import Literal
from typing_extensions import TypedDict


class Todo(TypedDict):
    """Todo to track."""

    content: str
    status: Literal["pending", "in_progress", "completed"]


class FileEntry(TypedDict):
    """Rich file entry with content and metadata."""
    
    content: str
    metadata: NotRequired[Dict[str, Any]]


def file_reducer(left, right):
    """Reducer for files that merges dictionaries safely for concurrent updates."""
    if left is None:
        left = {}
    if right is None:
        right = {}
    
    # Merge dictionaries, with right taking precedence for conflicts
    # This allows multiple parallel nodes to add different files concurrently
    result = {**left, **right}
    return result


class DeepAgentState(AgentState):
    todos: NotRequired[list[Todo]]
    files: Annotated[NotRequired[dict[str, FileEntry]], file_reducer]
