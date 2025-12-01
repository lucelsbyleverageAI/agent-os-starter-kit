"""State schema for tools_agent with optional sandbox support.

When sandbox is disabled, only the messages field is used (backward compatible).
When sandbox is enabled, sandbox_id and published_files are also available.
"""

from typing import Annotated, List
from typing_extensions import TypedDict, NotRequired
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from agent_platform.agents.deepagents.skills_deepagent.state import (
    PublishedFile,
    published_files_reducer,
)


class ToolsAgentState(TypedDict):
    """State for tools_agent with optional sandbox support.

    Fields:
        messages: Conversation history
        sandbox_id: E2B sandbox ID for reconnection (only used when sandbox_enabled=True)
        published_files: Files published by the agent for user download (only used when sandbox_enabled=True)
    """
    messages: Annotated[list[BaseMessage], add_messages]
    sandbox_id: NotRequired[str]
    published_files: Annotated[NotRequired[List[PublishedFile]], published_files_reducer]
