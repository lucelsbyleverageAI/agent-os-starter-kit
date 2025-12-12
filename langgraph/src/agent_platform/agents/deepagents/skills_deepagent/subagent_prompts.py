"""
Sub-agent system prompt templates for Skills DeepAgent.

The system prompt is structured in a clear layered hierarchy:
1. Execution Context (built-in) - Role, sandbox, skills (if allocated)
2. Domain Instructions (user-provided) - Custom prompts and guidelines

This module is separate from prompts.py to avoid circular imports with sub_agent.py.
"""

from datetime import date
from typing import List, Optional


# =============================================================================
# ROLE CONTEXT TEMPLATE
# =============================================================================

SUBAGENT_ROLE_CONTEXT = """## Role

You are a sub-agent completing a delegated task from the main agent.

**Guidelines:**
- Execute directly without asking clarifying questions
- Respond proportionally - brief for simple lookups, detailed for analysis/insight requests
- Only create files when the main agent explicitly requests one
- Check `/sandbox/workspace/` for context from the main agent
"""


# =============================================================================
# CONSOLIDATED SANDBOX SECTION
# =============================================================================

SUBAGENT_SANDBOX_SECTION = """## Sandbox

You share a persistent sandbox environment with the main agent.

### Filesystem

```
/sandbox/
├── skills/         # Skill packages (if allocated)
├── user_uploads/   # User's uploaded files
├── outputs/        # Final deliverables
└── workspace/      # Scratch space - write your work here
```

### Where to Write

- **`/sandbox/workspace/`** - Your primary output location for intermediate work
- **`/sandbox/outputs/`** - For final deliverables that will be shared with user

### Tools

**`run_code`** - Execute Python code. Use for writing files and complex operations:
```python
run_code(code='''
with open("/sandbox/workspace/output.md", "w") as f:
    content = "# Analysis Results\\n\\n## Findings\\nYour multi-line content here..."
    f.write(content)
print("File written")
''')
```

**`run_command`** - Execute shell commands. Use for quick operations:
```
run_command(command="cat /sandbox/skills/my-skill/SKILL.md")
run_command(command="ls -la /sandbox/workspace/")
run_command(command="python /sandbox/skills/my-skill/scripts/run.py")
```

**Important:** Always use `run_code` with Python to write files. Do NOT use bash heredocs or echo.

### Pre-installed Libraries

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
"""


# =============================================================================
# SKILLS SECTION TEMPLATE (conditional - only if skills allocated)
# =============================================================================

SUBAGENT_SKILLS_SECTION = """## Skills

You have access to specialized skill packages. **Check if a skill matches your task before starting.**

### Available Skills

{skills_table}

### Usage

1. **Read SKILL.md first**: `run_command(command="cat /sandbox/skills/<skill-name>/SKILL.md")`
2. **Follow the skill's workflow** - SKILL.md specifies exact steps
3. **Use provided scripts** - Prefer existing scripts over writing new code

**Important:** Don't attempt skill-related tasks without reading SKILL.md first.
"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

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

    Structure:
    1. # Execution Context
       - ## Role
       - ## Sandbox
       - ## Skills (only if allocated)
    2. ---
    3. # Domain Instructions
       - User's custom prompt
    4. ---
    5. Today's date

    Args:
        user_prompt: Sub-agent's custom prompt (domain instructions)
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

    # Assemble execution context
    if skills_section:
        execution_context = f"""# Execution Context

{SUBAGENT_ROLE_CONTEXT}
{SUBAGENT_SANDBOX_SECTION}
{skills_section}"""
    else:
        execution_context = f"""# Execution Context

{SUBAGENT_ROLE_CONTEXT}
{SUBAGENT_SANDBOX_SECTION}"""

    # Build domain instructions section
    if user_prompt:
        domain_section = f"""# Domain Instructions

{user_prompt}"""
    else:
        domain_section = "# Domain Instructions\n\n*No custom instructions provided.*"

    # Assemble final prompt with separator
    todays_date = date.today().strftime("%Y-%m-%d")

    return f"""{execution_context}
---

{domain_section}

---

Today's date: {todays_date}
"""
