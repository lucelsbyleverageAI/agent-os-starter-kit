# Skills Feature Implementation Plan

## Reference Documentation

**Anthropic Official Documentation:**
- [Agent Skills Overview](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/overview) - Core concepts and architecture
- [Agent Skills Quickstart](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/quickstart) - Getting started guide
- [Agent Skills Best Practices](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/best-practices) - Authoring guidance
- [Skills API Guide](https://docs.anthropic.com/en/docs/build-with-claude/skills-guide) - API integration

**Engineering Deep Dive:**
- [Equipping Agents for the Real World with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) - Architecture blog post

**Examples & Cookbooks:**
- [Claude Skills Cookbook](https://github.com/anthropics/claude-cookbooks/tree/main/skills) - Official examples including custom skills

---

## Overview

This document outlines the comprehensive plan for implementing Claude-style Agent Skills in the Agent OS platform. Skills are modular capability packages that extend agent functionality through filesystem-based instructions, scripts, and resources.

### Key Benefits
- **Progressive disclosure**: Only skill name/description loaded upfront (~100 tokens each), full content loaded on-demand
- **Filesystem-based context sharing**: Replace LangGraph state-as-filesystem with true E2B sandbox filesystem
- **Reusable capabilities**: Create once, use across agents and users
- **Large output handling**: Write to files instead of returning in context window

---

## Architecture Overview

### New Agent: DeepAgent with Skills

A new agent template that extends the existing DeepAgent architecture with:
1. **Built-in E2B filesystem tool** (not via MCP - direct integration)
2. **Skill loading system** (metadata in system prompt, files in sandbox)
3. **Shared filesystem architecture** for inter-agent communication
4. **Optional MCP tools** (user-configurable, same as current DeepAgent)
5. **Optional RAG/Knowledge** (same as current DeepAgent)

### Filesystem Structure (E2B Sandbox)

```
/sandbox/
├── skills/                    # Read-only, uploaded at thread start
│   ├── sales-deck-creator/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   └── apply_template.py
│   │   └── resources/
│   │       └── template.pptx
│   └── financial-analysis/
│       ├── SKILL.md
│       └── scripts/
│           └── calculate_ratios.py
├── shared/                    # Read-write, inter-agent context sharing
│   ├── research/              # Sub-agent findings
│   ├── drafts/                # Work-in-progress
│   └── context.md             # Shared context document
├── outputs/                   # Final deliverables for user download
│   └── final_report.pdf
└── workspace/                 # Private scratch space per agent
    ├── main_agent/
    └── research_subagent/
```

---

## Component Breakdown

### 1. Database Schema (LangConnect)

**New Tables:**

```sql
-- Skills metadata table
CREATE TABLE langconnect.skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) NOT NULL,
    description VARCHAR(1024) NOT NULL,
    storage_path TEXT NOT NULL,           -- Path in Supabase storage bucket
    pip_requirements TEXT[],              -- Optional pip packages to install
    created_by TEXT NOT NULL,             -- User ID
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    -- Note: Public status is managed via public_skill_permissions table, not here

    CONSTRAINT valid_skill_name CHECK (
        name ~ '^[a-z0-9-]+$' AND
        LENGTH(name) <= 64 AND
        name NOT LIKE '%anthropic%' AND
        name NOT LIKE '%claude%'
    )
);

-- Skills permissions table (mirrors collection_permissions pattern)
CREATE TABLE langconnect.skill_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID NOT NULL REFERENCES langconnect.skills(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    permission_level TEXT NOT NULL CHECK (permission_level IN ('viewer', 'editor', 'owner')),
    granted_by TEXT NOT NULL,  -- 'system:public' for auto-granted from public permissions
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(skill_id, user_id)
);

-- Public skill permissions table (mirrors public_collection_permissions pattern)
-- This tracks which skills are publicly available to all users
CREATE TABLE langconnect.public_skill_permissions (
    id SERIAL PRIMARY KEY,
    skill_id UUID NOT NULL REFERENCES langconnect.skills(id) ON DELETE CASCADE,
    permission_level TEXT NOT NULL DEFAULT 'viewer' CHECK (permission_level IN ('viewer', 'editor')),
    created_by UUID NOT NULL,              -- Admin who created the public permission
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,                -- NULL if active, timestamp if revoked
    revoke_mode TEXT CHECK (revoke_mode IN ('revoke_all', 'future_only')),
    notes TEXT,                            -- Optional admin notes

    UNIQUE(skill_id)  -- Only one public permission per skill (active or revoked)
);

-- Indexes
CREATE INDEX idx_skills_created_by ON langconnect.skills(created_by);
CREATE INDEX idx_skill_permissions_user ON langconnect.skill_permissions(user_id);
CREATE INDEX idx_skill_permissions_skill ON langconnect.skill_permissions(skill_id);
CREATE INDEX idx_public_skill_permissions_active ON langconnect.public_skill_permissions(skill_id) WHERE revoked_at IS NULL;

-- Trigger function: Auto-grant public skill permissions to new users
-- This should be added to the existing user signup trigger
CREATE OR REPLACE FUNCTION langconnect.grant_public_skill_permissions_to_user()
RETURNS TRIGGER AS $$
BEGIN
    -- Grant all active public skill permissions to the new user
    INSERT INTO langconnect.skill_permissions (skill_id, user_id, permission_level, granted_by)
    SELECT
        psp.skill_id,
        NEW.user_id,
        psp.permission_level,
        'system:public'
    FROM langconnect.public_skill_permissions psp
    WHERE psp.revoked_at IS NULL
    ON CONFLICT (skill_id, user_id) DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add trigger to user_roles table (mirrors existing pattern for collections/graphs/assistants)
-- Note: This should be added to the existing after_user_role_insert trigger
```

**New Storage Bucket:**

```sql
-- Skills storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'skills',
    'skills',
    false,
    104857600,  -- 100MB limit per skill zip
    ARRAY[
        'application/zip',
        'application/x-zip-compressed'
    ]
);

-- RLS Policies for skills bucket
CREATE POLICY "Users can upload to owned skills"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'skills' AND
    storage.user_has_skill_permission(
        (storage.foldername(name))[1]::uuid,
        auth.uid(),
        'editor'
    )
);

CREATE POLICY "Users can read accessible skills"
ON storage.objects FOR SELECT
TO authenticated
USING (
    bucket_id = 'skills' AND
    storage.user_has_skill_permission(
        (storage.foldername(name))[1]::uuid,
        auth.uid(),
        'viewer'
    )
);

-- Helper function for RLS policies
CREATE OR REPLACE FUNCTION storage.user_has_skill_permission(
    p_skill_uuid UUID,
    p_user_id UUID,
    p_min_permission TEXT DEFAULT 'viewer'
) RETURNS BOOLEAN AS $$
DECLARE
    v_permission_rank INTEGER;
    v_required_rank INTEGER;
    v_public_permission_level TEXT;
BEGIN
    -- Permission ranking
    v_required_rank := CASE p_min_permission
        WHEN 'viewer' THEN 1
        WHEN 'editor' THEN 2
        WHEN 'owner' THEN 3
        ELSE 0
    END;

    -- Check if skill has an active public permission
    SELECT permission_level INTO v_public_permission_level
    FROM langconnect.public_skill_permissions
    WHERE skill_id = p_skill_uuid AND revoked_at IS NULL;

    IF v_public_permission_level IS NOT NULL THEN
        -- Public permission exists - check if it meets minimum requirement
        v_permission_rank := CASE v_public_permission_level
            WHEN 'viewer' THEN 1
            WHEN 'editor' THEN 2
            ELSE 0
        END;
        IF v_permission_rank >= v_required_rank THEN
            RETURN TRUE;
        END IF;
    END IF;

    -- Check user's direct permission
    SELECT CASE permission_level
        WHEN 'viewer' THEN 1
        WHEN 'editor' THEN 2
        WHEN 'owner' THEN 3
        ELSE 0
    END INTO v_permission_rank
    FROM langconnect.skill_permissions
    WHERE skill_id = p_skill_uuid AND user_id = p_user_id::text;

    RETURN COALESCE(v_permission_rank >= v_required_rank, FALSE);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

---

### 2. LangConnect API (Backend)

**New File:** `apps/langconnect/langconnect/api/skills.py`

```python
# API Endpoints - Skills CRUD

POST   /skills                    # Upload new skill (zip file)
GET    /skills                    # List accessible skills (includes public skills)
GET    /skills/{id}               # Get skill metadata
GET    /skills/{id}/download      # Download skill zip for sandbox mounting
DELETE /skills/{id}               # Delete skill (owner only)
PUT    /skills/{id}               # Update skill (re-upload zip)
POST   /skills/{id}/share         # Share skill with users
GET    /skills/{id}/permissions   # List skill permissions
DELETE /skills/{id}/permissions/{user_id}  # Revoke access

# Admin endpoints
GET    /skills/admin/all          # List all skills (admin only)
```

**Public Permissions Router:** Add to `apps/langconnect/langconnect/api/public_permissions.py`

```python
# Public Skill Permission Endpoints (admin only)
# Mirrors the pattern used for collections, graphs, and assistants

GET    /public-permissions/skills                      # List all public skill permissions
POST   /public-permissions/skills                      # Create public skill permission
DELETE /public-permissions/skills/{skill_id}           # Revoke public skill permission
POST   /public-permissions/skills/{skill_id}/re-invoke # Re-invoke revoked permission
```

**Public Permission Models:**

```python
class PublicSkillPermissionItem(PublicPermissionItem):
    skill_id: str
    created_by: str

class CreatePublicSkillRequest(BaseModel):
    skill_id: str
    permission_level: str  # 'viewer' or 'editor'
    notes: Optional[str] = None
```

**Public Permission Behavior:**

When a public skill permission is created:
1. Record is inserted into `public_skill_permissions` table
2. Permission is immediately granted to ALL existing users via `skill_permissions` table
3. `granted_by` is set to `'system:public'` to track auto-granted permissions
4. New users automatically get access when they sign up (via user creation trigger)

When a public skill permission is revoked:
- `revoke_mode = 'future_only'`: Existing users keep access, new users don't get it
- `revoke_mode = 'revoke_all'`: Remove all `skill_permissions` where `granted_by = 'system:public'`

When re-invoked:
1. `revoked_at` is set back to NULL
2. Permission is re-granted to all existing users
```

**New File:** `apps/langconnect/langconnect/models/skill.py`

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class PermissionLevel(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

class SkillMetadata(BaseModel):
    id: UUID
    name: str = Field(..., max_length=64, pattern=r'^[a-z0-9-]+$')
    description: str = Field(..., max_length=1024)
    storage_path: str
    pip_requirements: Optional[List[str]] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    # Note: is_public is derived from public_skill_permissions table, not stored here
    is_public: bool = False  # Computed field based on active public permission

class SkillPermission(BaseModel):
    skill_id: UUID
    user_id: str
    permission_level: PermissionLevel
    granted_by: str

class SkillUploadRequest(BaseModel):
    # Multipart form with zip file
    pass

class SkillShareRequest(BaseModel):
    user_id: str
    permission_level: PermissionLevel = PermissionLevel.VIEWER
```

**Validation Logic:**

On skill upload:
1. Accept zip file via multipart form
2. Extract and validate structure:
   - Must contain `SKILL.md` at root
   - Parse YAML frontmatter for `name` and `description`
   - Validate name format (lowercase, hyphens, numbers only, max 64 chars)
   - Validate description (non-empty, max 1024 chars)
   - Check for forbidden words ("anthropic", "claude")
3. Store zip in Supabase storage: `skills/{skill_id}/skill.zip`
4. Create database record with extracted metadata
5. Create owner permission for uploading user

---

### 3. LangGraph Agent (DeepAgent with Skills)

**New Directory:** `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/`

**Files:**
- `__init__.py`
- `graph.py` - Main graph definition
- `configuration.py` - Config schema with skills support
- `prompts.py` - System prompt templates
- `sandbox_tools.py` - E2B filesystem tools

#### 3.1 Configuration Schema

**File:** `configuration.py`

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from agent_platform.agents.deepagents.basic_deepagent.configuration import (
    MCPConfig, RagConfig
)

class SkillReference(BaseModel):
    """Reference to a skill allocated to this agent"""
    skill_id: str
    name: str
    description: str

class SkillsConfig(BaseModel):
    """Skills configuration for the agent"""
    skills: List[SkillReference] = Field(
        default_factory=list,
        description="Skills allocated to this agent"
    )

class SandboxConfig(BaseModel):
    """E2B sandbox configuration"""
    timeout_seconds: int = Field(default=600, ge=60, le=3600)
    pip_packages: List[str] = Field(default_factory=list)

# Extended SubAgentConfig with skills support
class SkillsSubAgentConfig(BaseModel):
    """Configuration for a sub-agent with skills support.

    Extends the base SubAgentConfig pattern to include skills allocation.
    """
    name: str = Field(...)
    description: str = Field(...)
    prompt: str = Field(default="")  # Custom instructions for this sub-agent
    model_name: Optional[str] = Field(default="anthropic:claude-sonnet-4-5-20250929")

    # Existing capabilities
    mcp_config: Optional[MCPConfig] = Field(default=None)
    rag_config: Optional[RagConfig] = Field(default=None)

    # NEW: Skills for this sub-agent
    skills_config: Optional[SkillsConfig] = Field(
        default=None,
        metadata={
            "x_oap_ui_config": {
                "type": "skills_picker",
                "description": "Skills available to this sub-agent"
            }
        }
    )

class GraphConfigPydantic(BaseModel):
    """Configuration for DeepAgent with Skills"""

    model_name: str = Field(
        default="anthropic:claude-sonnet-4-5-20250929",
        json_schema_extra={"x_oap_ui_config": {"type": "model_select"}}
    )

    system_prompt: str = Field(
        default="",  # User's custom instructions - base prompt appended at runtime
        json_schema_extra={
            "x_oap_ui_config": {
                "type": "runbook",
                "title": "System Prompt",
                "description": "Custom instructions for this agent"
            }
        }
    )

    skills_config: Optional[SkillsConfig] = Field(
        default=None,
        json_schema_extra={
            "x_oap_ui_config": {
                "type": "skills_picker",
                "title": "Skills",
                "description": "Select skills to enable for this agent"
            }
        }
    )

    sandbox_config: SandboxConfig = Field(
        default_factory=SandboxConfig,
        json_schema_extra={
            "x_oap_ui_config": {
                "type": "sandbox_config",
                "title": "Sandbox Settings"
            }
        }
    )

    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        json_schema_extra={"x_oap_ui_config": {"type": "mcp_picker"}}
    )

    rag: Optional[RagConfig] = Field(
        default=None,
        json_schema_extra={"x_oap_ui_config": {"type": "rag_picker"}}
    )

    # Uses SkillsSubAgentConfig instead of base SubAgentConfig
    sub_agents: List[SkillsSubAgentConfig] = Field(
        default_factory=list,
        json_schema_extra={"x_oap_ui_config": {"type": "agents_builder"}}
    )

    include_general_purpose_agent: bool = Field(
        default=True,
        json_schema_extra={"x_oap_ui_config": {"type": "boolean"}}
    )

    recursion_limit: int = Field(
        default=100,
        json_schema_extra={"x_oap_ui_config": {"type": "number"}}
    )
```

#### 3.2 System Prompt Structure

**File:** `prompts.py`

The system prompt is structured so that:
1. User's custom `system_prompt` comes FIRST (their role, instructions, etc.)
2. Platform-provided appendix comes AFTER (filesystem, skills, date)

This allows users to define their agent's role and behavior, while the platform automatically appends the technical context about available capabilities.

```python
from datetime import date

# This gets APPENDED to the user's system prompt
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
- `/skills/` - Read-only. Contains skill packages with SKILL.md instructions and resources.
- `/shared/` - Read-write. Share context with sub-agents by writing files here.
- `/outputs/` - Read-write. Place final deliverables here for user download.
- `/workspace/` - Read-write. Your private scratch space.

**Best practices:**
- Write large outputs to files instead of returning in messages
- Write context to `/shared/` before delegating to sub-agents
- Use absolute paths when referencing files
- Only read skill files when needed for the current task

## Available Skills

{skills_table}

**To use a skill:**
1. Read the skill's instructions: `cat /skills/<skill-name>/SKILL.md`
2. Follow the instructions in SKILL.md
3. Run any referenced scripts: `python /skills/<skill-name>/scripts/<script>.py`
4. Access resources at `/skills/<skill-name>/resources/`

---

Today's date: {todays_date}
"""

def build_skills_table(skills: list) -> str:
    """Build markdown table of available skills"""
    if not skills:
        return "*No skills allocated to this agent.*"

    lines = ["| Skill | Description |", "|-------|-------------|"]
    for skill in skills:
        lines.append(f"| `{skill.name}` | {skill.description} |")
    return "\n".join(lines)

def build_system_prompt(config) -> str:
    """
    Build complete system prompt.

    Structure:
    1. User's custom system_prompt (their role, instructions)
    2. Platform appendix (filesystem, skills, date)
    """
    # User's custom instructions come first
    user_prompt = config.system_prompt or ""

    # Build skills table
    skills_table = build_skills_table(
        config.skills_config.skills if config.skills_config else []
    )

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

def build_subagent_system_prompt(subagent_config, agent_name: str) -> str:
    """
    Build system prompt for a sub-agent.

    Same structure as main agent but with sub-agent's own skills.
    """
    user_prompt = subagent_config.prompt or ""

    skills_table = build_skills_table(
        subagent_config.skills_config.skills if subagent_config.skills_config else []
    )

    appendix = PLATFORM_PROMPT_APPENDIX.format(
        skills_table=skills_table,
        todays_date=date.today().strftime("%Y-%m-%d")
    )

    if user_prompt:
        return f"{user_prompt}\n{appendix}"
    else:
        return appendix.strip()
```

#### 3.3 Sandbox Tools

**File:** `sandbox_tools.py`

**Design Decision:** We provide a single `sandbox` tool that executes bash commands, rather than separate tools for each operation (read_file, list_directory, etc.). This approach:

1. **Simpler tool surface**: One tool to learn instead of many
2. **Matches the system prompt**: We tell the agent to use `ls`, `cat`, `grep`, etc.
3. **More flexible**: Agent can compose complex commands, pipe outputs, etc.
4. **Matches Claude's native capabilities**: Claude Code uses bash commands extensively

The agent uses standard Unix commands as documented in the system prompt appendix.

```python
from langchain_core.tools import tool
from e2b_code_interpreter import Sandbox
from typing import Optional
import os

# Sandbox instances keyed by thread_id
_sandboxes: dict[str, Sandbox] = {}

def get_or_create_sandbox(
    thread_id: str,
    skills: list,
    pip_packages: list = None,
    timeout: int = 600
) -> Sandbox:
    """Get existing sandbox or create new one with skills uploaded"""

    if thread_id in _sandboxes:
        return _sandboxes[thread_id]

    # Create new sandbox
    sandbox = Sandbox(timeout=timeout)

    # Create directory structure
    sandbox.files.make_dir("/sandbox/skills")
    sandbox.files.make_dir("/sandbox/shared")
    sandbox.files.make_dir("/sandbox/shared/research")
    sandbox.files.make_dir("/sandbox/shared/drafts")
    sandbox.files.make_dir("/sandbox/outputs")
    sandbox.files.make_dir("/sandbox/workspace")

    # Upload skills (downloaded from Supabase storage)
    for skill in skills:
        skill_dir = f"/sandbox/skills/{skill.name}"
        sandbox.files.make_dir(skill_dir)
        # Upload skill files from storage
        upload_skill_to_sandbox(sandbox, skill)

    # Install pip packages if specified
    all_packages = set(pip_packages or [])
    for skill in skills:
        if skill.pip_requirements:
            all_packages.update(skill.pip_requirements)

    if all_packages:
        sandbox.commands.run(f"pip install {' '.join(all_packages)}")

    _sandboxes[thread_id] = sandbox
    return sandbox

@tool
def sandbox(
    command: str,
    timeout_seconds: int = 120
) -> str:
    """
    Execute a command in the sandbox environment.

    Use standard bash commands to interact with the filesystem:
    - List files: ls -la /sandbox/skills/
    - Read files: cat /sandbox/skills/my-skill/SKILL.md
    - Search: grep -r "pattern" /sandbox/
    - Run Python: python /sandbox/skills/my-skill/scripts/run.py
    - Write files: echo "content" > /sandbox/outputs/result.txt
    - And any other bash commands

    Args:
        command: The bash command to execute
        timeout_seconds: Command timeout in seconds (default: 120)

    Returns:
        Command output (stdout and stderr combined)

    Example:
        sandbox(command="cat /sandbox/skills/brand-guidelines/SKILL.md")
        sandbox(command="python /sandbox/skills/analysis/scripts/run.py input.csv")
        sandbox(command="ls -la /sandbox/shared/")
    """
    # Implementation gets sandbox from context (thread_id) and executes command
    # Returns stdout + stderr, truncated if too long
    pass

# Keep write_todos from existing deep_agent_toolkit.py
from agent_platform.agents.deepagents.deep_agent_toolkit import write_todos
```

**Note on write_todos:** We keep the `write_todos` tool as it provides a structured way to track task progress that's rendered nicely in the UI. This is separate from filesystem operations.

#### 3.4 Graph Definition

**File:** `graph.py`

```python
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage

from .configuration import GraphConfigPydantic
from .prompts import build_system_prompt
from .sandbox_tools import sandbox, write_todos, get_or_create_sandbox
from agent_platform.agents.deepagents.builder import build_subagent_tools
from agent_platform.utils.tool_utils import (
    create_collection_tools,
    fetch_mcp_tools
)
from agent_platform.utils.model_utils import get_model

def graph(config: dict):
    """Build DeepAgent with Skills graph"""

    cfg = GraphConfigPydantic(**config.get("configurable", {}))

    # Build system prompt with skills
    system_prompt = build_system_prompt(cfg)

    # Core built-in tools (always included)
    # - sandbox: Execute bash commands in E2B environment
    # - write_todos: Track task progress (rendered in UI)
    builtin_tools = [sandbox, write_todos]

    all_tools = list(builtin_tools)

    # Add MCP tools if configured
    if cfg.mcp_config and cfg.mcp_config.tools:
        mcp_tools = fetch_mcp_tools(cfg.mcp_config, config)
        all_tools.extend(mcp_tools)

    # Add RAG tools if configured
    if cfg.rag and cfg.rag.collections:
        rag_tools = create_collection_tools(cfg.rag, config)
        all_tools.extend(rag_tools)

    # Add sub-agent tools
    if cfg.sub_agents or cfg.include_general_purpose_agent:
        subagent_tools = build_subagent_tools(cfg, config)
        all_tools.extend(subagent_tools)

    # Get model
    model = get_model(cfg.model_name)

    # Create graph
    graph = create_react_agent(
        model=model,
        tools=all_tools,
        state_modifier=SystemMessage(content=system_prompt),
        checkpointer=MemorySaver()
    )

    return graph
```

#### 3.5 Register in langgraph.json

```json
{
  "graphs": {
    "deepagent": "./src/agent_platform/agents/deepagents/basic_deepagent/graph.py:graph",
    "skills_deepagent": "./src/agent_platform/agents/deepagents/skills_deepagent/graph.py:graph",
    ...
  }
}
```

---

### 4. Frontend Implementation

#### 4.1 Skills Page

**New Route:** `apps/web/src/app/(main)/skills/page.tsx`

Features:
- Grid/list view of accessible skills
- Upload new skill button
- Search and filter
- Permission indicators (owned, shared, public)

**Components:**
- `skills-gallery.tsx` - Grid of skill cards
- `skill-card.tsx` - Individual skill display
- `upload-skill-dialog.tsx` - Skill upload modal
- `skill-permissions-dialog.tsx` - Share/manage access
- `skill-detail-sheet.tsx` - View skill details

#### 4.2 Skill Card Component

```typescript
// apps/web/src/features/skills/components/skill-card.tsx

interface SkillCardProps {
  skill: {
    id: string;
    name: string;
    description: string;
    created_by: string;
    is_public: boolean;
    permission_level: 'owner' | 'editor' | 'viewer';
  };
  onEdit?: () => void;
  onDelete?: () => void;
  onShare?: () => void;
}

export function SkillCard({ skill, onEdit, onDelete, onShare }: SkillCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="font-mono text-sm">{skill.name}</CardTitle>
          <Badge variant={skill.is_public ? "default" : "secondary"}>
            {skill.is_public ? "Public" : skill.permission_level}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground line-clamp-3">
          {skill.description}
        </p>
      </CardContent>
      <CardFooter>
        <DropdownMenu>
          {/* Edit, Share, Delete actions based on permission */}
        </DropdownMenu>
      </CardFooter>
    </Card>
  );
}
```

#### 4.3 Upload Skill Dialog

```typescript
// apps/web/src/features/skills/components/upload-skill-dialog.tsx

interface UploadSkillDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export function UploadSkillDialog({ open, onOpenChange, onSuccess }: UploadSkillDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<ValidationResult | null>(null);

  const handleFileSelect = async (file: File) => {
    setFile(file);
    setValidating(true);

    // Client-side validation
    const result = await validateSkillZip(file);
    setValidation(result);
    setValidating(false);
  };

  const handleUpload = async () => {
    if (!file || !validation?.valid) return;

    const formData = new FormData();
    formData.append('file', file);

    await fetch('/api/langconnect/skills', {
      method: 'POST',
      body: formData
    });

    onSuccess();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload Skill</DialogTitle>
          <DialogDescription>
            Upload a zip file containing SKILL.md and any supporting files.
          </DialogDescription>
        </DialogHeader>

        <FileDropzone
          accept={{ 'application/zip': ['.zip'] }}
          onDrop={handleFileSelect}
        />

        {validating && <Spinner />}

        {validation && (
          <ValidationPreview
            name={validation.name}
            description={validation.description}
            files={validation.files}
            errors={validation.errors}
          />
        )}

        <DialogFooter>
          <Button onClick={handleUpload} disabled={!validation?.valid}>
            Upload Skill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

#### 4.4 Skills Picker for Agent Config

**New Component:** `apps/web/src/features/chat/components/configuration-sidebar/config-field-skills.tsx`

```typescript
interface ConfigFieldSkillsProps {
  value: SkillsConfig;
  onChange: (value: SkillsConfig) => void;
}

export function ConfigFieldSkills({ value, onChange }: ConfigFieldSkillsProps) {
  const { skills, isLoading } = useAccessibleSkills();

  const selectedSkillIds = value?.skills?.map(s => s.skill_id) || [];

  const handleToggleSkill = (skill: Skill) => {
    const isSelected = selectedSkillIds.includes(skill.id);

    if (isSelected) {
      onChange({
        skills: value.skills.filter(s => s.skill_id !== skill.id)
      });
    } else {
      onChange({
        skills: [
          ...value.skills,
          {
            skill_id: skill.id,
            name: skill.name,
            description: skill.description
          }
        ]
      });
    }
  };

  return (
    <div className="space-y-2">
      <Label>Skills</Label>
      <p className="text-sm text-muted-foreground">
        Select skills to enable for this agent
      </p>

      <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
        {skills.map(skill => (
          <SkillCheckbox
            key={skill.id}
            skill={skill}
            checked={selectedSkillIds.includes(skill.id)}
            onCheckedChange={() => handleToggleSkill(skill)}
          />
        ))}
      </div>
    </div>
  );
}
```

#### 4.5 Agent Form Integration

Update `agent-form.tsx` to include skills picker when graph type is `skills_deepagent`:

```typescript
// In agent-form.tsx, add to configuration tab:

{graphType === 'skills_deepagent' && (
  <ConfigFieldSkills
    value={form.watch('skills_config')}
    onChange={(value) => form.setValue('skills_config', value)}
  />
)}
```

---

### 5. API Routes (Next.js Proxy)

**New Routes:**

```
apps/web/src/app/api/langconnect/skills/
├── route.ts                    # GET (list), POST (upload)
├── [id]/
│   ├── route.ts                # GET, PUT, DELETE
│   ├── download/route.ts       # GET (download zip)
│   ├── share/route.ts          # POST
│   └── permissions/
│       └── route.ts            # GET, DELETE
```

---

### 6. Sub-Agent Skills Access

Sub-agents in the DeepAgent hierarchy need access to skills allocated to them. The approach:

1. **All skills mounted in sandbox**: Every skill allocated to any agent/sub-agent is uploaded to `/sandbox/skills/`
2. **Per-agent visibility in prompt**: Each agent's system prompt only lists the skills it has access to
3. **Shared filesystem**: All agents share the same sandbox (keyed by thread_id)

```python
# In builder.py for sub-agents

def build_subagent_system_prompt(subagent_config, parent_config):
    """Build system prompt for sub-agent with its allocated skills"""

    # Get skills allocated to this specific sub-agent
    subagent_skills = subagent_config.skills or []

    # Build skills table for this sub-agent only
    skills_table = build_skills_table(subagent_skills)

    # Sub-agent gets filesystem instructions + its skills
    return SUB_AGENT_PROMPT.format(
        skills_table=skills_table,
        custom_instructions=subagent_config.system_prompt or ""
    )
```

---

## Implementation Phases

### Phase 1: Database & Storage (Week 1)

1. Create database migration for `skills` and `skill_permissions` tables
2. Create `skills` storage bucket with RLS policies
3. Add helper function `user_has_skill_permission()`
4. Test storage and permissions locally

**Files to create/modify:**
- `database/migrations/langconnect/004_create_skills.sql`

### Phase 2: LangConnect API (Week 1-2)

1. Create skill models (`models/skill.py`)
2. Implement skill validation logic (zip parsing, SKILL.md validation)
3. Create skills API endpoints (`api/skills.py`)
4. Add permission management functions (`database/skills_permissions.py`)
5. Write API tests

**Files to create:**
- `apps/langconnect/langconnect/models/skill.py`
- `apps/langconnect/langconnect/api/skills.py`
- `apps/langconnect/langconnect/database/skills_permissions.py`
- `apps/langconnect/langconnect/services/skill_validation.py`

### Phase 3: LangGraph Agent (Week 2-3)

1. Create `skills_deepagent` directory structure
2. Implement configuration schema with skills support
3. Build system prompt templates
4. Implement E2B sandbox tools
5. Create graph definition
6. Register in `langgraph.json`
7. Test agent locally with mock skills

**Files to create:**
- `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/__init__.py`
- `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/configuration.py`
- `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/prompts.py`
- `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/sandbox_tools.py`
- `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/graph.py`

### Phase 4: Frontend - Skills Management (Week 3-4)

1. Create skills page route
2. Implement skills gallery component
3. Build upload skill dialog with validation
4. Add skill card component
5. Implement permissions dialog
6. Add API routes for skills

**Files to create:**
- `apps/web/src/app/(main)/skills/page.tsx`
- `apps/web/src/features/skills/components/skills-gallery.tsx`
- `apps/web/src/features/skills/components/skill-card.tsx`
- `apps/web/src/features/skills/components/upload-skill-dialog.tsx`
- `apps/web/src/features/skills/components/skill-permissions-dialog.tsx`
- `apps/web/src/features/skills/hooks/use-skills.ts`
- `apps/web/src/app/api/langconnect/skills/route.ts`
- `apps/web/src/app/api/langconnect/skills/[id]/route.ts`

### Phase 5: Frontend - Agent Integration (Week 4)

1. Create skills picker component
2. Update agent form to support skills_deepagent
3. Add skills to config field renderer
4. Test end-to-end agent creation with skills

**Files to create/modify:**
- `apps/web/src/features/chat/components/configuration-sidebar/config-field-skills.tsx`
- `apps/web/src/features/agents/components/create-edit-agent-dialogs/agent-form.tsx` (modify)

### Phase 6: Testing & Documentation (Week 5)

1. Create sample skills for testing
2. End-to-end testing of full flow
3. Performance testing (sandbox startup, skill loading)
4. Write user documentation
5. Update CLAUDE.md with skills architecture

---

## Sample Skills for Testing

### 1. Brand Guidelines Skill

```
brand-guidelines/
├── SKILL.md
├── resources/
│   ├── colors.json
│   └── logo.png
└── scripts/
    └── validate_colors.py
```

**SKILL.md:**
```yaml
---
name: brand-guidelines
description: Apply company brand guidelines to documents. Use when creating presentations, documents, or any branded materials.
---

# Brand Guidelines

## Colors
- Primary: #0066CC (Acme Blue)
- Secondary: #003366 (Acme Navy)
- Accent: #FF6600 (Acme Orange)

See `resources/colors.json` for full palette.

## Usage
1. Read color palette: `cat /skills/brand-guidelines/resources/colors.json`
2. Validate colors in document: `python /skills/brand-guidelines/scripts/validate_colors.py <file>`
```

### 2. Code Review Skill

```
code-review/
├── SKILL.md
└── scripts/
    ├── analyze_complexity.py
    └── check_style.py
```

---

## Security Considerations

1. **Skill Validation**: Strict validation of SKILL.md format and content
2. **Storage Isolation**: Skills stored in separate bucket with RLS
3. **Permission Enforcement**: Always check permissions before skill access
4. **Sandbox Isolation**: E2B sandboxes are isolated per thread
5. **No Network in Skills**: Skills cannot make external network calls (E2B limitation)
6. **Audit Logging**: Log skill uploads, shares, and usage

---

## Future Enhancements

1. **Skill Versioning**: Track versions when skills are updated
2. **Skill Marketplace**: Public skill discovery and sharing
3. **S3 Mounting**: Mount skills bucket directly instead of uploading files
4. **Skill Templates**: Pre-built skill templates for common tasks
5. **Skill Analytics**: Track skill usage and effectiveness
6. **Skill Dependencies**: Skills can declare dependencies on other skills

---

## Open Questions

1. **Skill Size Limits**: What's the maximum skill zip size? (Proposed: 100MB)
2. **Pip Package Allowlist**: Should we restrict which pip packages skills can request?
3. **Skill Execution Timeout**: What's the timeout for skill script execution?

---

## Appendix: SKILL.md Specification

### Required Fields

```yaml
---
name: skill-name        # Required: 1-64 chars, lowercase, hyphens, numbers only
description: ...        # Required: 1-1024 chars, what the skill does and when to use it
---
```

### Optional Fields

```yaml
---
name: skill-name
description: ...
pip_requirements:       # Optional: pip packages to install
  - pandas
  - openpyxl
---
```

### Body Format

The body of SKILL.md should contain:
1. Quick start / overview
2. Available scripts and how to use them
3. Available resources and their purpose
4. Examples of common usage patterns
5. Limitations or constraints

---

## Appendix: Directory Structure Summary

```
langgraph/
└── src/agent_platform/agents/deepagents/
    ├── basic_deepagent/           # Existing
    └── skills_deepagent/          # NEW
        ├── __init__.py
        ├── configuration.py
        ├── prompts.py
        ├── sandbox_tools.py
        └── graph.py

apps/langconnect/langconnect/
├── api/
│   ├── skills.py                  # NEW - Skills CRUD endpoints
│   └── public_permissions.py      # MODIFY - Add public skill permission endpoints
├── models/
│   └── skill.py                   # NEW
├── database/
│   └── skills_permissions.py      # NEW - SkillPermissionsManager class
└── services/
    └── skill_validation.py        # NEW

apps/web/src/
├── app/
│   ├── (main)/skills/
│   │   └── page.tsx               # NEW
│   └── api/langconnect/skills/
│       ├── route.ts               # NEW
│       └── [id]/
│           └── route.ts           # NEW
└── features/
    └── skills/                    # NEW
        ├── components/
        │   ├── skills-gallery.tsx
        │   ├── skill-card.tsx
        │   ├── upload-skill-dialog.tsx
        │   └── skill-permissions-dialog.tsx
        └── hooks/
            └── use-skills.ts

database/migrations/langconnect/
└── 004_create_skills.sql          # NEW
```
