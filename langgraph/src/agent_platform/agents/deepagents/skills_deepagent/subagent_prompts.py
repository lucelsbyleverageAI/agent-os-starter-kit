"""Sub-agent system prompt templates for Skills DeepAgent.

This module provides prompt templates for sub-agents in the Skills DeepAgent system.
It is separate from prompts.py to avoid circular imports with sub_agent.py.

Key differences from base deepagent subagent_prompts:
1. No "Context from Main Agent" section (context is in /sandbox/shared/)
2. References run_code and run_command tools explicitly
3. Includes user_uploads directory in structure
4. Emphasizes using run_code for file writing (not bash)
"""

from datetime import date
from typing import List, Optional


# Platform appendix for SUB-AGENTS in Skills DeepAgent
SUBAGENT_PLATFORM_PROMPT_APPENDIX = """
---

## Sub-Agent Execution Context

You are a sub-agent completing a delegated task.

**Guidelines:**
- Execute directly without asking clarifying questions
- Be concise - detailed outputs go in files
- Reference files you create in your response

---

## Sandbox Tools

You have two tools for interacting with the shared sandbox:

### `run_code` - For writing files and complex operations
```
run_code(code='''
with open("/sandbox/shared/output.md", "w") as f:
    content = "# Analysis Results\\n\\n## Findings\\nYour multi-line content here..."
    f.write(content)
print("File written")
''')

### `run_command` - For quick shell operations
```
run_command(command="cat /sandbox/skills/my-skill/SKILL.md")
run_command(command="ls -la /sandbox/shared/")
run_command(command="python /sandbox/skills/my-skill/scripts/run.py")
```

**Important:** Always use `run_code` with Python to write files. Do NOT use bash heredocs or echo.

---

## Pre-installed Libraries

The following libraries are available immediately (no `pip install` needed):

**Document Processing:**
- `pypdf`, `pdfplumber`, `PyMuPDF` (fitz) - PDF reading, text/table extraction
- `python-docx` - Word documents (.docx)
- `python-pptx` - PowerPoint (.pptx)
- `openpyxl`, `xlrd` - Excel files (.xlsx, .xls)

**Data Processing:**
- `pandas`, `numpy` - DataFrames and numerical computing
- `beautifulsoup4`, `lxml` - HTML/XML parsing
- `markdownify` - HTML to Markdown
- `Pillow` - Image processing
- `chardet` - Encoding detection

**Utilities:**
- `requests`, `httpx` - HTTP clients
- `pyyaml`, `python-dateutil`, `tabulate`

---

## Sandbox Filesystem

You share a persistent sandbox with the main agent:

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

{skills_section}

---

## Guidelines

- **Use `run_code` for writing**: Python handles multi-line content properly
- **Use `run_command` for reading**: `cat`, `ls`, `head` for quick operations
- Write detailed outputs to `/sandbox/shared/`
- Return a concise summary with file references
- Use absolute paths like `/sandbox/shared/output.md`

---

Today's date: {todays_date}
"""


# Skills section for sub-agents (only included if skills are allocated)
SUBAGENT_SKILLS_SECTION = """
## Skills

You have access to specialized skill packages. **Check if a skill matches your task before starting.**

### Available Skills

{skills_table}

### When to Use Skills

- Does your task domain match a skill's description?
- Would the skill's resources (templates, scripts, data) help?

**If a skill is relevant, read its SKILL.md first.**

### How to Use a Skill

**Step 1: Read the skill's instructions (required)**
```python
run_command(command="cat /sandbox/skills/<skill-name>/SKILL.md")
```

**Step 2: Follow the skill's workflow**
SKILL.md contains the steps, scripts to run, and resources available.

**Step 3: Use provided scripts**
```python
run_command(command="python /sandbox/skills/<skill-name>/scripts/<script>.py [arguments]")
```
Prefer existing scripts over writing new code.

**Important**: Don't attempt skill-related tasks without reading SKILL.md first.
"""


def build_skills_table(skills: Optional[List] = None) -> str:
    """
    Build markdown table of available skills.

    Args:
        skills: List of skill references with name and description

    Returns:
        Markdown table string or empty string if no skills
    """
    if not skills:
        return ""

    lines = ["| Skill | Description |", "|-------|-------------|"]
    for skill in skills:
        # Handle both dict and object access patterns
        name = skill.get("name", "") if isinstance(skill, dict) else getattr(skill, "name", "")
        description = skill.get("description", "") if isinstance(skill, dict) else getattr(skill, "description", "")
        lines.append(f"| `{name}` | {description} |")

    return "\n".join(lines)


def build_subagent_system_prompt(
    user_prompt: Optional[str] = None,
    skills: Optional[List] = None
) -> str:
    """
    Build system prompt for a sub-agent in Skills DeepAgent.

    Sub-agents get specialized instructions that:
    1. Frame them as working on a delegated task from the main agent
    2. Emphasize stateless execution without asking clarifying questions
    3. Guide them to use /sandbox/shared/ for output
    4. Reference execute_in_sandbox tool
    5. Conditionally include skills if allocated

    Args:
        user_prompt: Sub-agent's custom prompt
        skills: List of skill references for this sub-agent

    Returns:
        Complete system prompt string
    """
    # Build skills section conditionally
    if skills:
        skills_table = build_skills_table(skills)
        skills_section = SUBAGENT_SKILLS_SECTION.format(skills_table=skills_table)
    else:
        skills_section = ""

    # Build platform appendix for sub-agent
    appendix = SUBAGENT_PLATFORM_PROMPT_APPENDIX.format(
        skills_section=skills_section,
        todays_date=date.today().strftime("%Y-%m-%d")
    )

    # Combine: user prompt + platform appendix
    if user_prompt:
        return f"{user_prompt}\n{appendix}"
    else:
        return appendix.strip()
