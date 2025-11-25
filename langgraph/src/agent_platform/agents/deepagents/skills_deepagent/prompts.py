"""
System prompt templates for Skills DeepAgent.

The system prompt is structured so that:
1. User's custom system_prompt comes FIRST (their role, instructions, etc.)
2. Platform-provided appendix comes AFTER (filesystem, skills, date)

This allows users to define their agent's role and behavior, while the platform
automatically appends the technical context about available capabilities.
"""

from datetime import date
from typing import List, Optional


# Platform appendix that gets added after user's custom instructions
PLATFORM_PROMPT_APPENDIX = """
---

## Sandbox Filesystem

You have access to a persistent E2B sandbox with the following structure:

```
/sandbox/
├── skills/       # Read-only skill packages
├── shared/       # Read-write, shared with sub-agents
├── outputs/      # Final deliverables for the user
└── workspace/    # Your private scratch space
```

**Using the filesystem:**
- Run bash commands: `ls`, `cat`, `grep`, `find`, `head`, `tail`, `wc`, etc.
- Execute code: `python script.py`, `node script.js`
- File operations: `cp`, `mv`, `mkdir`, `rm`, `touch`
- Text processing: `sed`, `awk`, `sort`, `uniq`

**Directory purposes:**
- `/sandbox/skills/` - Read-only. Contains skill packages with SKILL.md instructions and resources.
- `/sandbox/shared/` - Read-write. Share context with sub-agents by writing files here.
- `/sandbox/outputs/` - Read-write. Place final deliverables here for user download.
- `/sandbox/workspace/` - Read-write. Your private scratch space.

**Best practices:**
- Write large outputs to files instead of returning in messages
- Write context to `/sandbox/shared/` before delegating to sub-agents
- Use absolute paths when referencing files
- Only read skill files when needed for the current task

## Available Skills

{skills_table}

**To use a skill:**
1. Read the skill's instructions: `cat /sandbox/skills/<skill-name>/SKILL.md`
2. Follow the instructions in SKILL.md
3. Run any referenced scripts: `python /sandbox/skills/<skill-name>/scripts/<script>.py`
4. Access resources at `/sandbox/skills/<skill-name>/resources/`

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
    skills: Optional[List] = None
) -> str:
    """
    Build complete system prompt.

    Structure:
    1. User's custom system_prompt (their role, instructions)
    2. Platform appendix (filesystem, skills, date)

    Args:
        user_prompt: User's custom system prompt
        skills: List of skill references

    Returns:
        Complete system prompt string
    """
    # Build skills table
    skills_table = build_skills_table(skills)

    # Build platform appendix
    appendix = PLATFORM_PROMPT_APPENDIX.format(
        skills_table=skills_table,
        todays_date=date.today().strftime("%Y-%m-%d")
    )

    # Combine: user prompt + platform appendix
    if user_prompt:
        return f"{user_prompt}\n{appendix}"
    else:
        return appendix.strip()


def build_subagent_system_prompt(
    user_prompt: Optional[str] = None,
    skills: Optional[List] = None
) -> str:
    """
    Build system prompt for a sub-agent.

    Same structure as main agent but with sub-agent's own skills.

    Args:
        user_prompt: Sub-agent's custom prompt
        skills: List of skill references for this sub-agent

    Returns:
        Complete system prompt string
    """
    # Sub-agents use the same structure
    return build_system_prompt(user_prompt, skills)
