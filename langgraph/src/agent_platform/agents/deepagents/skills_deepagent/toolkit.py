"""Toolkit for Skills DeepAgent - write_todos only.

This toolkit contains only the write_todos tool with a condensed description.
All file operations are handled via the execute_in_sandbox tool (sandbox_tools.py).
"""

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from typing import Annotated

try:
    from .state import Todo, SkillsDeepAgentState
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.state import Todo, SkillsDeepAgentState


# Condensed write_todos description (~400 tokens instead of ~2000)
WRITE_TODOS_DESCRIPTION = """Track and manage tasks for complex work.

**When to use**: Multi-step tasks, user provides multiple items, tasks requiring planning.
**When NOT to use**: Single trivial tasks, purely informational requests.

**States**: pending, in_progress, completed
**Rules**:
- Only ONE task in_progress at a time
- Mark completed IMMEDIATELY after finishing
- Only mark completed if FULLY done (no errors, no partial work)

Example:
```json
[
  {"content": "Research topic", "status": "completed"},
  {"content": "Write summary", "status": "in_progress"},
  {"content": "Review and finalize", "status": "pending"}
]
```
"""


@tool(description=WRITE_TODOS_DESCRIPTION)
def write_todos(
    todos: list[Todo],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Update the todo list."""
    return Command(
        update={
            "todos": todos,
            "messages": [
                ToolMessage(f"Updated todo list to {todos}", tool_call_id=tool_call_id)
            ],
        }
    )
