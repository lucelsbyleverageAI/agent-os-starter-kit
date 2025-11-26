# Skills & Filesystem Prompts Improvement Plan

## Problem Statement

The current skills and filesystem instructions in the platform prompts are too minimal, causing agents to:
1. Not recognize when to use available skills
2. Not understand the workflow for skill invocation (read SKILL.md → follow instructions → use resources)
3. Underutilize the filesystem for context sharing between agents

## Current State Analysis

### Main Agent Prompt (`prompts.py`)
Current issues:
- Skills table only shows name + description with no decision-making guidance
- "To use a skill" section is procedural but lacks **when** to use skills
- No emphasis on reading SKILL.md as the **first step** before attempting any skill-related task
- Filesystem instructions are generic, not outcome-oriented

### Sub-Agent Prompt (`subagent_prompts.py`)
Current issues:
- Skills section is even more minimal (just copied pattern)
- No guidance on skill priority vs other tools
- Filesystem usage is described but not connected to workflow

---

## Improvement Plan

### 1. Add "Skills-First" Decision Framework

**Goal**: Make agents recognize when skills are relevant and prioritize skill usage.

**Changes to both prompts:**

```markdown
## Skills

Skills are specialized capability packages that provide domain-specific instructions,
scripts, and resources. **When you have skills allocated, they should be your first
consideration for relevant tasks.**

### When to Use Skills

Before starting any task, check if an available skill matches the task:
- Does the task domain match a skill's description?
- Does the user mention keywords related to a skill?
- Would the skill's resources (templates, scripts, data) be useful?

**If a skill is relevant, ALWAYS read its SKILL.md first.** The skill's instructions
will guide you on the correct approach, available resources, and any scripts to run.
```

### 2. Enhance Skills Table with "Use When" Column

**Goal**: Make skill selection easier with explicit trigger conditions.

**Current:**
```
| Skill | Description |
|-------|-------------|
| `brand-guidelines` | Apply company brand guidelines to documents |
```

**Improved:**
```
| Skill | Description | Use When |
|-------|-------------|----------|
| `brand-guidelines` | Apply company brand guidelines to documents | User mentions branding, colors, logos, style guides, or creating branded materials |
```

**Implementation note**: This requires skills to have a `use_when` field in their metadata, or we derive it from the description. Initially, we can auto-generate a "Use When" hint from the description.

### 3. Add Explicit Skill Invocation Workflow

**Goal**: Clear step-by-step process that agents can follow.

**Add to both prompts:**

```markdown
### How to Use a Skill

**Step 1: Read the skill's instructions**
```bash
cat /sandbox/skills/<skill-name>/SKILL.md
```
This file contains everything you need: overview, workflows, available scripts, and resources.

**Step 2: Follow the skill's workflow**
- SKILL.md will specify the exact steps for different scenarios
- It may reference additional files in `scripts/` or `resources/`

**Step 3: Use provided scripts for deterministic operations**
```bash
python /sandbox/skills/<skill-name>/scripts/<script>.py [arguments]
```
Scripts handle complex operations reliably. Prefer running scripts over reimplementing logic.

**Step 4: Access resources as needed**
- Templates: `/sandbox/skills/<skill-name>/resources/`
- Reference data: Check SKILL.md for what's available

**Important**: Do NOT attempt skill-related tasks without first reading SKILL.md.
The instructions contain critical context you need.
```

### 4. Connect Filesystem to Workflow Outcomes

**Goal**: Make filesystem usage purposeful, not just available.

**Improved main agent filesystem section:**

```markdown
## Sandbox Filesystem

You have a persistent E2B sandbox for code execution and file management.

### Directory Structure & Purpose

```
/sandbox/
├── skills/       # Read-only. Skill packages with instructions and resources.
├── shared/       # Read-write. Context sharing with sub-agents.
├── outputs/      # Read-write. Final deliverables for user download.
└── workspace/    # Read-write. Your private scratch space.
```

### Workflow Patterns

**Before delegating to a sub-agent:**
1. Write relevant context to `/sandbox/shared/context.md`
2. Include: task background, constraints, relevant data
3. Reference this file when invoking the sub-agent

**When producing deliverables:**
1. Create files in `/sandbox/outputs/`
2. Name clearly: `final_report.pdf`, `analysis_results.xlsx`
3. Tell the user: "Your deliverable is ready at `/sandbox/outputs/filename`"

**For intermediate work:**
1. Use `/sandbox/workspace/` for drafts and experiments
2. Move finalized content to `/outputs/` or `/shared/`

### Available Commands

File operations: `ls`, `cat`, `head`, `tail`, `grep`, `find`, `wc`
Modifications: `cp`, `mv`, `mkdir`, `rm`, `touch`
Text processing: `sed`, `awk`, `sort`, `uniq`
Code execution: `python script.py`, `node script.js`
```

### 5. Sub-Agent Specific Enhancements

**Goal**: Sub-agents understand their role in the skill/filesystem workflow.

**Add to sub-agent prompt:**

```markdown
### Using Skills as a Sub-Agent

If you have skills allocated, follow the same skill workflow:
1. Read SKILL.md first
2. Follow its instructions
3. Use provided scripts

**Key difference**: Write your detailed work to `/sandbox/shared/` so the main agent
can review it. Your response should be a summary with file references.

### Context from Main Agent

Check `/sandbox/shared/` for context the main agent may have prepared:
- `context.md` - Background and constraints
- `input/` - Data files to process
- `requirements.md` - Specific requirements

Read relevant files before starting your task.
```

### 6. Add Negative Guidance (What NOT to Do)

**Goal**: Prevent common mistakes.

**Add to both prompts:**

```markdown
### Common Mistakes to Avoid

- **Don't skip SKILL.md**: Never attempt a skill-related task without reading instructions first
- **Don't reinvent scripts**: If a skill has a script for an operation, use it instead of writing new code
- **Don't return large outputs in messages**: Write to files and reference them
- **Don't leave work in `/workspace/`**: Move deliverables to `/outputs/` when complete
```

---

## Implementation Tasks

### Task 1: Update Main Agent Prompt (`prompts.py`)
- [ ] Add "Skills-First" decision framework section
- [ ] Add explicit skill invocation workflow
- [ ] Enhance filesystem section with workflow patterns
- [ ] Add negative guidance section
- [ ] Keep total addition under 800 tokens (balance detail vs context cost)

### Task 2: Update Sub-Agent Prompt (`subagent_prompts.py`)
- [ ] Add skill decision framework (shorter version)
- [ ] Add skill invocation workflow (same as main agent)
- [ ] Add "Context from Main Agent" section
- [ ] Add sub-agent specific filesystem guidance
- [ ] Add negative guidance (subset)

### Task 3: Enhance Skills Table Builder
- [ ] Consider adding "Use When" column auto-generated from description
- [ ] Or: Add a prompt that tells agent to infer usage triggers from descriptions

### Task 4: Update Default Prompts in Configuration
- [ ] Review `DEFAULT_SYSTEM_PROMPT` in `configuration.py`
- [ ] Review `DEFAULT_SUB_AGENT_PROMPT` in `configuration.py`
- [ ] Ensure they work well with the new platform appendix

---

## Success Criteria

After implementation, agents should:
1. Proactively check skills when starting relevant tasks
2. Always read SKILL.md before attempting skill-related work
3. Use provided scripts instead of reimplementing logic
4. Write deliverables to appropriate directories
5. Share context via filesystem when delegating to sub-agents

---

## Token Budget Considerations

Current platform appendix: ~400 tokens
Target after improvements: ~800-1000 tokens

This is acceptable because:
- Skills provide significant value when used correctly
- Better instructions reduce wasted turns from incorrect approaches
- The appendix only loads once per conversation

---

## Files to Modify

1. `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/prompts.py`
   - `PLATFORM_PROMPT_APPENDIX` constant

2. `langgraph/src/agent_platform/agents/deepagents/subagent_prompts.py`
   - `SUBAGENT_PLATFORM_PROMPT_APPENDIX` constant
   - `SUBAGENT_SKILLS_SECTION` constant

3. `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/configuration.py`
   - `DEFAULT_SYSTEM_PROMPT` constant
   - `DEFAULT_SUB_AGENT_PROMPT` constant
