"""
Sub-agent system prompt templates.

This module provides prompt templates for sub-agents in the DeepAgent system.
It is intentionally separate from skills_deepagent/prompts.py to avoid
circular import issues (sub_agent.py is imported by graph.py, which is
imported by skills_deepagent/__init__.py).

The sub-agent prompts provide:
1. Behavioral guidelines for stateless task execution
2. Filesystem documentation for the shared E2B sandbox
3. Conditional skills documentation (if skills are allocated)
"""

from datetime import date
from typing import List, Optional


# Platform appendix for SUB-AGENTS
# Different framing than main agent - emphasizes stateless execution and context sharing
SUBAGENT_PLATFORM_PROMPT_APPENDIX = """
---

## Sub-Agent Execution Context

You are a sub-agent working on a delegated task from the main agent.

**Behavioral Guidelines:**
- Execute your task directly without asking clarifying questions
- This is a stateless interaction - work with the information provided
- Be concise and actionable in your response
- Write detailed outputs to files; return a summary with file references

**Response Format:**
- Provide a clear summary of what you accomplished
- Reference files you created: "See `/sandbox/shared/research/findings.md` for details"
- If the task couldn't be completed, explain what's missing and what you attempted

---

## Context from Main Agent

Before starting, check `/sandbox/shared/` for context the main agent may have prepared:
- `context.md` - Background information and constraints
- Input files or data to process
- Any specific requirements

Read relevant files to understand the full context of your task.

---

## Sandbox Filesystem

You share a persistent E2B sandbox with the main agent:

```
/sandbox/
├── skills/       # Read-only. Skill packages (if allocated).
├── shared/       # Read-write. Your primary output location.
├── outputs/      # Read-write. Final user deliverables (main agent typically writes here).
└── workspace/    # Read-write. Scratch space.
```

### Where to Write Your Work

- **`/sandbox/shared/`** - Your primary output location. The main agent will review files here.
- **`/sandbox/shared/research/`** - Research findings and analysis
- **`/sandbox/shared/drafts/`** - Work-in-progress content

### Available Commands

- File exploration: `ls`, `cat`, `head`, `tail`, `grep`, `find`
- File operations: `cp`, `mv`, `mkdir`, `touch`
- Code execution: `python script.py`

{skills_section}

---

## Important Guidelines

- **Check for context first**: Read any files in `/sandbox/shared/` before starting
- **Write to shared directory**: Put your outputs in `/sandbox/shared/` for the main agent
- **Summarize, don't dump**: Return a concise summary; detailed content goes in files
- **Use absolute paths**: Always use full paths like `/sandbox/shared/output.md`

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
```bash
cat /sandbox/skills/<skill-name>/SKILL.md
```

**Step 2: Follow the skill's workflow**
SKILL.md contains the steps, scripts to run, and resources available.

**Step 3: Use provided scripts**
```bash
python /sandbox/skills/<skill-name>/scripts/<script>.py [arguments]
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
    Build system prompt for a sub-agent.

    Sub-agents get specialized instructions that:
    1. Frame them as working on a delegated task from the main agent
    2. Emphasize stateless execution without asking clarifying questions
    3. Guide them to use /sandbox/shared/ for context sharing
    4. Conditionally include skills if allocated

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
