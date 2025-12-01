"""
System prompt templates for tools_agent.

The system prompt uses a two-layer structure:
1. Execution Context (built-in) - Role, sandbox, skills (when enabled)
2. Domain Instructions (user-provided) - Custom prompts and guidelines

When sandbox_enabled=False: Lightweight prompt with just role and domain instructions.
When sandbox_enabled=True: Full context including sandbox filesystem and skills.
"""

from datetime import date
from typing import List, Optional


# =============================================================================
# ROLE CONTEXT
# =============================================================================

ROLE_CONTEXT = """## Role

You are a helpful AI assistant with access to various tools.

**How to approach tasks:**
- Understand what the user needs before acting
- Use tools when they can help answer questions or complete requests
- Provide concise, well-structured responses
- Be proactive in suggesting relevant tools or approaches
"""


# =============================================================================
# SANDBOX CONTEXT (only included when sandbox_enabled=True)
# =============================================================================

SANDBOX_CONTEXT = """## Sandbox Environment

You have a persistent E2B sandbox for code execution and file processing.

### Filesystem

```
/sandbox/
├── skills/         # Read-only. Skill packages with instructions and resources.
├── user_uploads/   # Read-only. Files uploaded by the user.
├── outputs/        # Read-write. Final deliverables for user download.
└── workspace/      # Read-write. Your scratch space.
```

### Sandbox Tools

**`run_code`** - Execute Python code. Use for writing files and complex operations:
```python
run_code(code='''
with open("/sandbox/outputs/report.md", "w") as f:
    content = "# Report\\n\\nContent here."
    f.write(content)
print("File created")
''')
```

**`run_command`** - Execute shell commands. Use for quick operations:
```
run_command(command="ls -la /sandbox/user_uploads/")
run_command(command="cat /sandbox/skills/my-skill/SKILL.md")
```

**`publish_file_to_user`** - Share a created file with the user:
```
publish_file_to_user(
    file_path="/sandbox/outputs/report.docx",
    display_name="Report",
    description="Summary of findings"
)
```

**Important:** Always use `run_code` with Python to write files. Do NOT use bash heredocs.

### Pre-installed Libraries

Available immediately (no pip install needed):

**Document Processing:** pypdf, pdfplumber, python-docx, python-pptx, openpyxl
**Data Processing:** pandas, numpy, beautifulsoup4, Pillow
**Utilities:** requests, httpx, pyyaml, python-dateutil

### Workflow

1. User uploads appear in `/sandbox/user_uploads/`
2. Process files using run_code or run_command
3. Save outputs to `/sandbox/outputs/`
4. Use `publish_file_to_user` to share files with the user
"""


# =============================================================================
# SKILLS SECTION TEMPLATE
# =============================================================================

SKILLS_SECTION_TEMPLATE = """## Available Skills

{skills_table}

### Usage

1. **Read SKILL.md first**: `run_command(command="cat /sandbox/skills/<skill-name>/SKILL.md")`
2. **Follow the skill's workflow** - SKILL.md specifies exact steps
3. **Use provided scripts** - `run_command(command="python /sandbox/skills/.../scripts/run.py")`

**Important:** Don't attempt skill-related tasks without reading SKILL.md first.
"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def build_skills_table(skills: Optional[List] = None) -> str:
    """
    Build markdown table of available skills.

    Args:
        skills: List of SkillReference objects with name and description

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


def build_system_prompt(
    user_prompt: Optional[str] = None,
    sandbox_enabled: bool = False,
    skills: Optional[List] = None,
) -> str:
    """
    Build complete system prompt for tools_agent.

    Structure:
    1. # Execution Context
       - ## Role (always)
       - ## Sandbox Environment (only when sandbox_enabled)
       - ## Available Skills (only when skills allocated)
    2. ---
    3. # Domain Instructions (user's custom prompt)
    4. ---
    5. Today's date

    Args:
        user_prompt: User's custom system prompt (domain instructions)
        sandbox_enabled: Whether sandbox is enabled
        skills: List of skill references (only used when sandbox_enabled)

    Returns:
        Complete system prompt string
    """
    parts = ["# Execution Context\n"]
    parts.append(ROLE_CONTEXT)

    # Add sandbox context if enabled
    if sandbox_enabled:
        parts.append(SANDBOX_CONTEXT)

        # Add skills section if skills are allocated
        if skills:
            skills_table = build_skills_table(skills)
            if skills_table:
                skills_section = SKILLS_SECTION_TEMPLATE.format(skills_table=skills_table)
                parts.append(skills_section)

    parts.append("\n---\n")

    # Add domain instructions
    if user_prompt:
        parts.append(f"# Domain Instructions\n\n{user_prompt}")
    else:
        parts.append("# Domain Instructions\n\n*No custom instructions provided.*")

    parts.append("\n\n---\n")

    # Add timestamp
    parts.append(f"Today's date: {date.today().strftime('%Y-%m-%d')}")

    return "\n".join(parts)
