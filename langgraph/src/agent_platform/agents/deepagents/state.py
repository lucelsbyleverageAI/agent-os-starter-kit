from langgraph.prebuilt.chat_agent_executor import AgentState
from typing import NotRequired, Annotated, Any, Dict, Sequence
from typing import Literal
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


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
    # Optional field for trimmed/processed messages from pre_model_hook
    # When present, this takes precedence over 'messages' for model input
    llm_input_messages: NotRequired[Sequence[BaseMessage]]
