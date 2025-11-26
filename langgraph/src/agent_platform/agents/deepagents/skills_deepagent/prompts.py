"""
System prompt templates for Skills DeepAgent.

The system prompt is structured so that:
1. User's custom system_prompt comes FIRST (their role, instructions, etc.)
2. Platform-provided appendix comes AFTER (sandbox, skills, date)

This allows users to define their agent's role and behavior, while the platform
automatically appends the technical context about available capabilities.

Note: Sub-agent prompts are defined in ./subagent_prompts.py (local to skills_deepagent).
"""

from datetime import date
from typing import List, Optional

# Import from local subagent_prompts (not parent deepagents module)
try:
    from .subagent_prompts import build_subagent_system_prompt
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.subagent_prompts import build_subagent_system_prompt

__all__ = ["build_system_prompt", "build_subagent_system_prompt", "build_skills_table"]


# Built-in tools section (with task tool for sub-agents)
BUILTIN_TOOLS_WITH_TASK = """
---

## Built-in Tools

### write_todos
Use to track multi-step tasks. Mark tasks completed immediately when done.

### task
Delegate complex work to sub-agents. They share the sandbox filesystem.

### run_code
Execute code using the Jupyter-style interpreter. **Use for writing files and complex operations.**

### run_command
Execute shell commands. **Use for quick operations (ls, cat) and running scripts.**
"""

# Built-in tools section (without task tool)
BUILTIN_TOOLS_WITHOUT_TASK = """
---

## Built-in Tools

### write_todos
Use to track multi-step tasks. Mark tasks completed immediately when done.

### run_code
Execute code using the Jupyter-style interpreter. **Use for writing files and complex operations.**

### run_command
Execute shell commands. **Use for quick operations (ls, cat) and running scripts.**
"""

# Platform appendix that gets added after user's custom instructions (MAIN AGENT)
# Note: {builtin_tools} placeholder is filled based on whether sub-agents are available
PLATFORM_PROMPT_APPENDIX = """{builtin_tools}

---

## Sandbox Environment

You have access to a persistent E2B sandbox with two tools: `run_code` and `run_command`.

### Directory Structure

```
/sandbox/
├── skills/         # Read-only. Skill packages with instructions and resources.
├── user_uploads/   # Read-only. Files uploaded by the user.
├── shared/         # Read-write. Context sharing with sub-agents.
├── outputs/        # Read-write. Final deliverables for user download.
└── workspace/      # Read-write. Your private scratch space.
```

### Pre-installed Libraries

The following libraries are available immediately (no `pip install` needed):

**Document Processing:**
- `pypdf`, `pdfplumber`, `PyMuPDF` (fitz) - PDF reading, text/table extraction
- `python-docx` - Microsoft Word documents (.docx)
- `python-pptx` - PowerPoint presentations (.pptx)
- `openpyxl`, `xlrd` - Excel files (.xlsx, .xls)

**Data Processing:**
- `pandas`, `numpy` - DataFrames and numerical computing
- `beautifulsoup4`, `lxml` - HTML/XML parsing
- `markdownify` - Convert HTML to Markdown
- `Pillow` - Image processing
- `chardet` - Character encoding detection

**Utilities:**
- `requests`, `httpx` - HTTP clients
- `pyyaml` - YAML parsing
- `python-dateutil` - Date parsing
- `tabulate` - Pretty-print tables

### When to Use Each Tool

**`run_code`** - For writing files and complex operations (Python recommended):
```
run_code(code='with open("/sandbox/outputs/report.md", "w") as f:\\n    f.write("# Report Title\\n\\nContent here...")\\nprint("Done")')
```

Or with triple-quotes for complex content:
```
run_code(code='''
with open("/sandbox/outputs/report.md", "w") as f:
    content = "# Report Title\\n\\n## Summary\\nMulti-line content here."
    f.write(content)
print("File created")
''')

**`run_command`** - For quick shell operations:
```
run_command(command="ls -la /sandbox/skills/")
run_command(command="cat /sandbox/skills/my-skill/SKILL.md")
run_command(command="python /sandbox/skills/my-skill/scripts/run.py")
run_command(command="pip install pandas")
```

### Important: Writing Files

**Always use `run_code` with Python to write files.** Do NOT use bash heredocs, echo, or cat for writing - they fail with multi-line content.

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
```python
run_command(command="cat /sandbox/skills/<skill-name>/SKILL.md")
```

### Skill Workflow

1. **Read SKILL.md** - Contains overview, workflows, and available resources
2. **Follow instructions** - SKILL.md specifies exact steps
3. **Use provided scripts** - `run_command(command="python /sandbox/skills/.../scripts/run.py")`
4. **Access resources** - Templates and data in `/sandbox/skills/.../resources/`

---

## Important Guidelines

- **Use `run_code` for writing files**: Python handles multi-line content reliably
- **Use `run_command` for reading/listing**: Quick operations like `cat`, `ls`, `head`
- **Check user uploads first**: Files are in `/sandbox/user_uploads/`
- **Read SKILL.md before using skills**: Never skip this step
- **Use skill scripts**: Don't reinvent what scripts already do
- **Write outputs to files**: Don't return large content in messages
- **Use absolute paths**: Always use `/sandbox/...` paths

---

Today's date: {todays_date}
"""


def build_skills_table(skills: Optional[List] = None) -> str:
    """
    Build markdown table of available skills.

    Args:
        skills: List of SkillReference objects with name and description

    Returns:
        Markdown table string or message if no skills
    """
    if not skills:
        return "*No skills allocated to this agent.*"

    lines = ["| Skill | Description |", "|-------|-------------|"]
    for skill in skills:
        # Handle both dict and object access patterns
        name = skill.get("name", "") if isinstance(skill, dict) else getattr(skill, "name", "")
        description = skill.get("description", "") if isinstance(skill, dict) else getattr(skill, "description", "")
        lines.append(f"| `{name}` | {description} |")

    return "\n".join(lines)


def build_system_prompt(
    user_prompt: Optional[str] = None,
    skills: Optional[List] = None,
    has_subagents: bool = True
) -> str:
    """
    Build complete system prompt for main agent.

    Structure:
    1. User's custom system_prompt (their role, instructions)
    2. Built-in tools section
    3. Sandbox environment
    4. Skills
    5. Important guidelines
    6. Today's date

    Args:
        user_prompt: User's custom system prompt
        skills: List of skill references
        has_subagents: Whether task tool is available (sub-agents configured)

    Returns:
        Complete system prompt string
    """
    # Build skills table
    skills_table = build_skills_table(skills)

    # Select appropriate built-in tools section
    builtin_tools = BUILTIN_TOOLS_WITH_TASK if has_subagents else BUILTIN_TOOLS_WITHOUT_TASK

    # Build platform appendix
    appendix = PLATFORM_PROMPT_APPENDIX.format(
        builtin_tools=builtin_tools,
        skills_table=skills_table,
        todays_date=date.today().strftime("%Y-%m-%d")
    )

    # Combine: user prompt + platform appendix
    if user_prompt:
        return f"{user_prompt}\n{appendix}"
    else:
        return appendix.strip()
