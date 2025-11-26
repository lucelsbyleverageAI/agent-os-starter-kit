# Skills DeepAgent Refactor Plan

This document outlines a comprehensive refactoring of the Skills DeepAgent to:
1. Simplify tools to only `write_todos` and `execute_in_sandbox`
2. Remove state-based filesystem in favor of sandbox-only filesystem
3. Give sub-agents access to the sandbox tool
4. Improve prompts and reduce tool description verbosity
5. Handle user uploads via sandbox rather than state

**Important**: All changes should be made in the `skills_deepagent/` directory to keep the basic_deepagent backward compatible. We will create local copies of shared components rather than modifying the base implementation.

---

## Current Architecture Issues

### 1. Confusing Built-in Tools
The base `deepagents/graph.py` includes these built-in tools:
- `write_todos` - ✅ Keep
- `write_file` - ❌ Remove (uses state filesystem)
- `read_file` - ❌ Remove (uses state filesystem)
- `ls` - ❌ Remove (uses state filesystem)
- `edit_file` - ❌ Remove (uses state filesystem)

The skills_deepagent adds:
- `sandbox` tool - ✅ Keep but rename to `execute_in_sandbox`

### 2. State Filesystem vs Sandbox
Currently there are TWO filesystems:
- **State filesystem** (`state.files`) - In-memory dict, tools: write_file, read_file, ls, edit_file
- **E2B sandbox filesystem** (`/sandbox/`) - Real filesystem, tool: sandbox

This is confusing. Skills DeepAgent should ONLY use the sandbox.

### 3. Sub-agents Don't Have Sandbox Access
Sub-agents are created in `sub_agent.py:_get_agents()` with these built-in tools:
```python
all_builtin_tools = [write_todos, write_file, read_file, ls, edit_file]
```
They don't have access to the `sandbox` tool, so they can't interact with the E2B environment.

### 4. Verbose Tool Descriptions
- `write_todos`: ~185 lines, ~2000 tokens
- `task`: ~70 lines, ~800 tokens
- These bloat the system prompt unnecessarily

### 5. User Uploads Go to State, Not Sandbox
`file_attachment_processing.py` extracts user uploads into `state.files`. For skills_deepagent, these should go to `/sandbox/user_uploads/` instead.

### 6. Main Agent System Prompt Issues
- `base_prompt_with_task` from `graph.py` includes "Tool Authentication Errors" section - not needed
- Date is appended twice (once by `prompts.py`, once by `append_datetime_to_prompt`)
- Tools section appears after skills section (should be before)
- Format is disjointed

---

## Implementation Tasks

### Task 1: Create Skills-Specific State Schema

**File to create**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/state.py`

Create a simplified state that removes the `files` field:

```python
"""State schema for Skills DeepAgent - sandbox-only, no state filesystem."""

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
    """
    todos: NotRequired[list[Todo]]
```

---

### Task 2: Create Skills-Specific Toolkit

**File to create**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/toolkit.py`

Create a toolkit with ONLY `write_todos` (copied from base) and a condensed description:

```python
"""Toolkit for Skills DeepAgent - write_todos only."""

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from typing import Annotated

from .state import Todo, SkillsDeepAgentState

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
```

---

### Task 3: Rename Sandbox Tool to `execute_in_sandbox`

**File to modify**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/sandbox_tools.py`

Update `create_sandbox_tool()` to return a tool named `execute_in_sandbox` with clearer description:

```python
def create_sandbox_tool(thread_id: str):
    """Create sandbox execution tool bound to a specific thread."""

    @tool
    def execute_in_sandbox(
        command: str,
        timeout_seconds: int = 120
    ) -> str:
        """
        Execute a bash command in the E2B sandbox environment.

        The sandbox has a persistent filesystem at /sandbox/ with:
        - /sandbox/skills/ - Skill packages (read-only)
        - /sandbox/user_uploads/ - Files uploaded by the user
        - /sandbox/shared/ - Context sharing with sub-agents
        - /sandbox/outputs/ - Final deliverables for download
        - /sandbox/workspace/ - Your scratch space

        Examples:
            execute_in_sandbox(command="ls -la /sandbox/skills/")
            execute_in_sandbox(command="cat /sandbox/skills/my-skill/SKILL.md")
            execute_in_sandbox(command="python /sandbox/skills/my-skill/scripts/run.py")
            execute_in_sandbox(command="echo 'Hello' > /sandbox/outputs/result.txt")

        Args:
            command: Bash command to execute
            timeout_seconds: Timeout (default 120s, max 600s)

        Returns:
            Command output (stdout/stderr combined)
        """
        # ... existing implementation ...

    return execute_in_sandbox
```

---

### Task 4: Create Skills-Specific Sub-Agent Module

**File to create**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/sub_agent.py`

This is a modified copy of `deepagents/sub_agent.py` that:
1. Uses `SkillsDeepAgentState` instead of `DeepAgentState`
2. Includes `execute_in_sandbox` tool for all sub-agents (passed in from main agent)
3. Uses only `write_todos` as the built-in tool (no file tools)
4. Has a condensed `task` tool description

Key changes:

```python
# Import from skills_deepagent instead of base
from .state import SkillsDeepAgentState, Todo
from .toolkit import write_todos, WRITE_TODOS_DESCRIPTION
from .subagent_prompts import build_subagent_system_prompt  # Already exists

# Condensed TASK_DESCRIPTION (~400 tokens instead of ~800)
TASK_DESCRIPTION_PREFIX = """Delegate tasks to specialized sub-agents.

Available agents:
- general-purpose: Handles research, analysis, and multi-step tasks
{other_agents}
"""

TASK_DESCRIPTION_SUFFIX = """
**Usage**: Specify `subagent_type` to select which agent.

**Guidelines**:
- Sub-agents are stateless - provide complete context in your prompt
- They return a single response with their findings
- Tell them exactly what to do and what to return
- They share the sandbox filesystem at /sandbox/

**Do NOT use** for simple file reads or single operations you can do directly.
"""

# In _get_agents():
async def _get_agents(
    tools,  # Now includes execute_in_sandbox from main agent
    instructions,
    subagents,
    model,
    state_schema,
    post_model_hook=None,
    config=None,
    include_general_purpose=True,
):
    # Only write_todos as built-in (sandbox tool comes from `tools` param)
    all_builtin_tools = [write_todos]

    # ... rest of implementation, but using skills-specific imports
```

---

### Task 5: Create Skills-Specific File Attachment Processing

**File to create**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/file_attachment_processing.py`

Modified version that writes to sandbox instead of state:

```python
"""File attachment processing for Skills DeepAgent - writes to sandbox."""

import re
from typing import Annotated
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from agent_platform.sentry import get_logger

from .state import SkillsDeepAgentState
from .sandbox_tools import get_sandbox

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

    # ... parse attachments same as original ...

    sandbox = get_sandbox(thread_id)
    if not sandbox:
        logger.warning("[FILE_ATTACH] No sandbox available for uploads")
        return Command(update={})

    # Ensure user_uploads directory exists
    try:
        sandbox.files.make_dir("/sandbox/user_uploads")
    except:
        pass  # May already exist

    for attachment in attachments_found:
        filename = attachment['file_name']
        content = attachment['content']

        # Write to sandbox
        sandbox_path = f"/sandbox/user_uploads/{filename}.md"
        sandbox.files.write(sandbox_path, content.encode())
        logger.info(f"[FILE_ATTACH] Wrote {filename} to {sandbox_path}")

    # Return empty update - files are in sandbox, not state
    return Command(update={})
```

---

### Task 6: Create Skills-Specific Agent Builder

**File to create**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/agent_builder.py`

A local version of the agent builder that:
1. Uses `SkillsDeepAgentState`
2. Only includes `write_todos` and `execute_in_sandbox` as built-ins
3. Has a cleaner base prompt (no tool auth section, proper ordering)
4. Doesn't append date (prompts.py already does this)

```python
"""Agent builder for Skills DeepAgent."""

from typing import Sequence, Union, Callable, Any, Optional, Type, TypeVar
from langchain_core.tools import BaseTool, tool
from langchain_core.language_models import LanguageModelLike
from langgraph.types import Checkpointer
from langchain_core.runnables import RunnableConfig

from .state import SkillsDeepAgentState
from .toolkit import write_todos
from .sub_agent import _create_task_tool, _create_sync_task_tool
from agent_platform.agents.deepagents.custom_react_agent import custom_create_react_agent
from agent_platform.agents.deepagents.model import get_default_model
from agent_platform.utils.message_utils import create_image_preprocessor


StateSchema = TypeVar("StateSchema", bound=SkillsDeepAgentState)
StateSchemaType = Type[StateSchema]


# Clean base prompt - no tool auth section, minimal verbosity
BASE_PROMPT_WITH_TASK = """## Built-in Tools

### write_todos
Use to track multi-step tasks. Mark tasks completed immediately when done.

### task
Delegate complex work to sub-agents. They share the sandbox filesystem.

### execute_in_sandbox
Run bash commands in the E2B sandbox. Use for all file operations, code execution, and skill usage.
"""

BASE_PROMPT_WITHOUT_TASK = """## Built-in Tools

### write_todos
Use to track multi-step tasks. Mark tasks completed immediately when done.

### execute_in_sandbox
Run bash commands in the E2B sandbox. Use for all file operations, code execution, and skill usage.
"""


def skills_agent_builder(
    tools: Sequence[Union[BaseTool, Callable]],
    instructions: str,
    model: Optional[Union[str, LanguageModelLike]] = None,
    subagents: list = None,
    state_schema: Optional[StateSchemaType] = None,
    config_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    post_model_hook: Optional[Callable] = None,
    pre_model_hook: Optional[Callable] = None,
    is_async: bool = False,
    runnable_config: Optional[RunnableConfig] = None,
    include_general_purpose_agent: bool = True,
):
    """Build a Skills DeepAgent with sandbox-only filesystem."""

    has_subagents = (subagents and len(subagents) > 0) or include_general_purpose_agent

    # Build prompt: user instructions + base prompt
    # Note: instructions already includes skills/filesystem from prompts.py
    # Do NOT append date here - prompts.py already does it
    base_prompt = BASE_PROMPT_WITH_TASK if has_subagents else BASE_PROMPT_WITHOUT_TASK
    prompt = instructions + "\n\n" + base_prompt

    # Only write_todos as built-in - execute_in_sandbox comes from `tools`
    built_in_tools = [write_todos]

    if model is None:
        model = get_default_model()

    state_schema = state_schema or SkillsDeepAgentState

    # Get LangConnect URL for image preprocessing
    langconnect_api_url = "http://langconnect:8080"
    if runnable_config:
        rag_config = runnable_config.get("configurable", {}).get("rag", {})
        if isinstance(rag_config, dict):
            langconnect_api_url = rag_config.get("langconnect_api_url", langconnect_api_url)

    image_hook = create_image_preprocessor(langconnect_api_url)

    # Combine hooks
    combined_pre_hook = None
    if pre_model_hook and image_hook:
        async def combined_hook(state, config):
            trimming_result = pre_model_hook(state)
            state = {**state, **trimming_result}
            state = await image_hook(state, config)
            return state
        combined_pre_hook = combined_hook
    elif image_hook:
        combined_pre_hook = image_hook
    elif pre_model_hook:
        combined_pre_hook = pre_model_hook

    # Create task tool if sub-agents available
    if has_subagents:
        # Pass execute_in_sandbox to sub-agents via tools
        if not is_async:
            task_tool = _create_sync_task_tool(
                list(tools) + built_in_tools,  # includes execute_in_sandbox
                instructions,
                subagents or [],
                model,
                state_schema,
                post_model_hook,
                runnable_config,
                include_general_purpose_agent,
            )
        else:
            task_tool = _create_task_tool(
                list(tools) + built_in_tools,
                instructions,
                subagents or [],
                model,
                state_schema,
                post_model_hook,
                runnable_config,
                include_general_purpose_agent,
            )
        all_tools = built_in_tools + list(tools) + [task_tool]
    else:
        all_tools = built_in_tools + list(tools)

    return custom_create_react_agent(
        model,
        prompt=prompt,
        tools=all_tools,
        state_schema=state_schema,
        post_model_hook=post_model_hook,
        pre_model_hook=combined_pre_hook,
        config_schema=config_schema,
        checkpointer=checkpointer,
    )


def async_create_skills_agent(
    tools,
    instructions,
    model=None,
    subagents=None,
    state_schema=None,
    config_schema=None,
    checkpointer=None,
    post_model_hook=None,
    pre_model_hook=None,
    runnable_config=None,
    include_general_purpose_agent=True,
):
    """Create an async Skills DeepAgent."""
    return skills_agent_builder(
        tools=tools,
        instructions=instructions,
        model=model,
        subagents=subagents,
        state_schema=state_schema,
        config_schema=config_schema,
        checkpointer=checkpointer,
        post_model_hook=post_model_hook,
        pre_model_hook=pre_model_hook,
        is_async=True,
        runnable_config=runnable_config,
        include_general_purpose_agent=include_general_purpose_agent,
    )
```

---

### Task 7: Update Main Graph to Use New Components

**File to modify**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/graph.py`

Update imports and use new local components:

```python
# Change imports from:
from agent_platform.agents.deepagents.graph import async_create_deep_agent
from agent_platform.agents.deepagents.deep_agent_toolkit import write_todos

# To:
from .agent_builder import async_create_skills_agent
from .toolkit import write_todos
from .sandbox_tools import get_or_create_sandbox, create_sandbox_tool

# In graph() function:
async def graph(config: RunnableConfig):
    # ... existing config parsing ...

    tools = []

    # Initialize sandbox (ALWAYS, not just when skills exist)
    try:
        await get_or_create_sandbox(
            thread_id=thread_id,
            skills=skills,
            langconnect_url=langconnect_url,
            access_token=supabase_token,
            pip_packages=sandbox_pip_packages,
            timeout=sandbox_timeout
        )
        # Add execute_in_sandbox tool
        sandbox_tool = create_sandbox_tool(thread_id)
        tools.append(sandbox_tool)
    except Exception as e:
        logger.error(f"[skills_deepagent] Failed to initialize sandbox: {e}")
        raise  # Sandbox is required for skills_deepagent

    # Add MCP tools, RAG tools as before...

    # Use new agent builder
    agent = async_create_skills_agent(
        tools=tools,
        instructions=system_prompt,
        model=model,
        subagents=sub_agents_config,
        config_schema=GraphConfigPydantic,
        runnable_config=config,
        include_general_purpose_agent=cfg.include_general_purpose_agent,
        pre_model_hook=trimming_hook,
    )

    return agent
```

---

### Task 8: Update Prompts to Reflect New Architecture

**File to modify**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/prompts.py`

Update `PLATFORM_PROMPT_APPENDIX` to:
1. Put tools section BEFORE skills section
2. Reference `execute_in_sandbox` tool
3. Include `user_uploads/` in directory structure
4. Remove redundant date (will be added once by base prompt)

```python
PLATFORM_PROMPT_APPENDIX = """
---

## Sandbox Environment

You have access to a persistent E2B sandbox via the `execute_in_sandbox` tool.

### Directory Structure

```
/sandbox/
├── skills/         # Read-only. Skill packages with instructions and resources.
├── user_uploads/   # Read-only. Files uploaded by the user.
├── shared/         # Read-write. Context sharing with sub-agents.
├── outputs/        # Read-write. Final deliverables for user download.
└── workspace/      # Read-write. Your private scratch space.
```

### Using the Sandbox

All file operations use `execute_in_sandbox` with bash commands:
- List files: `execute_in_sandbox(command="ls -la /sandbox/skills/")`
- Read files: `execute_in_sandbox(command="cat /sandbox/user_uploads/data.xlsx.md")`
- Write files: `execute_in_sandbox(command="echo 'content' > /sandbox/outputs/result.txt")`
- Run Python: `execute_in_sandbox(command="python /sandbox/skills/my-skill/scripts/run.py")`

### Workflow Patterns

**When user uploads files**: Check `/sandbox/user_uploads/` for their content.

**Before delegating to sub-agents**: Write context to `/sandbox/shared/`.

**When producing deliverables**: Create files in `/sandbox/outputs/` and inform the user.

---

## Skills

Skills are specialized capability packages. **Check if a skill matches your task before starting.**

### Available Skills

{skills_table}

### When to Use Skills

- Does the task domain match a skill's description?
- Would the skill's resources (templates, scripts, data) help?

**If relevant, read the skill's SKILL.md first:**
```bash
execute_in_sandbox(command="cat /sandbox/skills/<skill-name>/SKILL.md")
```

### Skill Workflow

1. **Read SKILL.md** - Contains overview, workflows, and available resources
2. **Follow instructions** - SKILL.md specifies exact steps
3. **Use provided scripts** - Prefer `python /sandbox/skills/.../scripts/run.py` over writing new code
4. **Access resources** - Templates and data in `/sandbox/skills/.../resources/`

---

## Important Guidelines

- **Check user uploads first**: Files the user uploads are in `/sandbox/user_uploads/`
- **Read SKILL.md before using skills**: Never skip this step
- **Use skill scripts**: Don't reinvent what scripts already do
- **Write outputs to files**: Don't return large content in messages
- **Use absolute paths**: Always use `/sandbox/...` paths

---

Today's date: {todays_date}
"""
```

---

### Task 9: Update Sub-Agent Prompts

**File to modify**: `langgraph/src/agent_platform/agents/deepagents/subagent_prompts.py`

Remove "Context from Main Agent" section and update for sandbox:

```python
SUBAGENT_PLATFORM_PROMPT_APPENDIX = """
---

## Sub-Agent Execution Context

You are a sub-agent completing a delegated task.

**Guidelines:**
- Execute directly without asking clarifying questions
- Be concise - detailed outputs go in files
- Reference files you create in your response

---

## Sandbox Filesystem

You share a persistent E2B sandbox with the main agent:

```
/sandbox/
├── skills/         # Skill packages (if allocated)
├── user_uploads/   # User's uploaded files
├── shared/         # Context sharing - write your outputs here
├── outputs/        # Final deliverables
└── workspace/      # Scratch space
```

### Where to Write

- **`/sandbox/shared/`** - Your primary output location
- **`/sandbox/shared/research/`** - Research findings
- **`/sandbox/shared/drafts/`** - Work in progress

Use `execute_in_sandbox` for all file operations.

{skills_section}

---

## Guidelines

- Write detailed outputs to `/sandbox/shared/`
- Return a concise summary with file references
- Use absolute paths like `/sandbox/shared/output.md`

---

Today's date: {todays_date}
"""
```

---

### Task 10: Add `/sandbox/user_uploads/` to Sandbox Initialization

**File to modify**: `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/sandbox_tools.py`

In `get_or_create_sandbox()`, add:

```python
# Create directory structure
sandbox.files.make_dir("/sandbox/skills")
sandbox.files.make_dir("/sandbox/user_uploads")  # ADD THIS
sandbox.files.make_dir("/sandbox/shared")
sandbox.files.make_dir("/sandbox/shared/research")
sandbox.files.make_dir("/sandbox/shared/drafts")
sandbox.files.make_dir("/sandbox/outputs")
sandbox.files.make_dir("/sandbox/workspace")
```

---

## File Summary

### Files to CREATE in `skills_deepagent/`:
1. `state.py` - Simplified state without files
2. `toolkit.py` - write_todos with condensed description
3. `sub_agent.py` - Modified sub-agent module with sandbox support
4. `file_attachment_processing.py` - Writes to sandbox instead of state
5. `agent_builder.py` - Local agent builder

### Files to MODIFY in `skills_deepagent/`:
1. `sandbox_tools.py` - Rename tool, add user_uploads dir
2. `graph.py` - Use new local components
3. `prompts.py` - Update for new architecture

### Files to MODIFY in `deepagents/`:
1. `subagent_prompts.py` - Remove "Context from Main Agent", update for sandbox

### Files NOT to modify (keep backward compatible):
- `deepagents/graph.py`
- `deepagents/deep_agent_toolkit.py`
- `deepagents/deep_agent_toolkit_descriptions.py`
- `deepagents/state.py`
- `deepagents/sub_agent.py`
- `deepagents/file_attachment_processing.py`

---

## Testing Checklist

After implementation:

1. [ ] Main agent has only `write_todos`, `execute_in_sandbox`, and `task` tools (plus configured MCP/RAG)
2. [ ] Sub-agents have `write_todos` and `execute_in_sandbox` tools
3. [ ] User file uploads appear in `/sandbox/user_uploads/`
4. [ ] Skills are loaded to `/sandbox/skills/`
5. [ ] System prompt has correct order: Sandbox → Skills → Guidelines
6. [ ] No duplicate "Today's date" in prompt
7. [ ] No "Tool Authentication Errors" section in prompt
8. [ ] Task tool description is concise
9. [ ] Write_todos description is concise
10. [ ] Basic deepagent still works unchanged
