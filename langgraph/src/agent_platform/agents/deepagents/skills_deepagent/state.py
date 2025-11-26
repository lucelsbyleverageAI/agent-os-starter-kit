"""State schema for Skills DeepAgent - sandbox-only, no state filesystem.

Unlike the base DeepAgentState, this state does NOT include a `files` field.
All file operations happen in the E2B sandbox via the execute_in_sandbox tool.
"""

from langgraph.prebuilt.chat_agent_executor import AgentState
from typing import NotRequired, Literal
from typing_extensions import TypedDict


class Todo(TypedDict):
    """Todo item for task tracking."""
    content: str
    status: Literal["pending", "in_progress", "completed"]


class SkillsDeepAgentState(AgentState):
    """State for Skills DeepAgent.

    Unlike base DeepAgentState, this does NOT include a `files` field.
    All file operations happen in the E2B sandbox.

    Fields:
        messages: Conversation history (inherited from AgentState)
        todos: Task tracking list
    """
    todos: NotRequired[list[Todo]]
