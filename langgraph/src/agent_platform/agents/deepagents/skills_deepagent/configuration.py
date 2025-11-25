"""
Configuration schema for Skills DeepAgent.

This module defines the configuration schema for agents with skills support,
including skill references, sandbox settings, and sub-agent configurations.
"""

from typing import Optional, List
from pydantic import BaseModel, Field

from agent_platform.agents.deepagents.basic_deepagent.configuration import (
    RagConfig,
    MCPConfig,
    SubAgentConfig,
    DEFAULT_RECURSION_LIMIT,
)
from agent_platform.utils.model_utils import get_model_options_for_ui


# Graph metadata
GRAPH_NAME = "Skills Agent"
GRAPH_DESCRIPTION = "An advanced agent with E2B sandbox and skills support. Skills are modular capability packages that provide reusable instructions, scripts, and resources."


# Default prompts
DEFAULT_SYSTEM_PROMPT = """## Role
You are an expert AI assistant with access to an E2B sandbox environment and specialized skills.

## Task
Help the user accomplish their goals by:
- Using your sandbox environment to execute code and manage files
- Leveraging available skills for specialized tasks
- Delegating complex tasks to appropriate sub-agents
- Providing clear, concise responses to the user

## Guidelines
- Read skill instructions (SKILL.md) before using a skill
- Use the sandbox for code execution and file operations
- Write large outputs to files instead of returning in messages
- Keep your direct responses concise and to the point
"""

DEFAULT_SUB_AGENT_PROMPT = """## Role
You are a specialist sub-agent helping with a specific task delegated by the main agent.

## Task
Complete the delegated task using your available tools and sandbox environment.

## Guidelines
- Focus on completing the specific task you've been assigned
- Use the sandbox file system to store any context, findings, or work products
- Read skill instructions (SKILL.md) before using a skill
- Summarise what you've accomplished in your response
"""


class SkillReference(BaseModel):
    """
    Reference to a skill allocated to an agent.

    This is a lightweight reference containing only the essential metadata
    needed for the system prompt skills table.
    """
    skill_id: str = Field(..., description="UUID of the skill")
    name: str = Field(..., description="Skill name for the skills table")
    description: str = Field(..., description="Skill description for the skills table")


class SkillsConfig(BaseModel):
    """Skills configuration for an agent."""

    skills: List[SkillReference] = Field(
        default_factory=list,
        description="Skills allocated to this agent"
    )


class SandboxConfig(BaseModel):
    """E2B sandbox configuration."""

    timeout_seconds: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Sandbox timeout in seconds (60-3600)"
    )
    pip_packages: List[str] = Field(
        default_factory=list,
        description="Additional pip packages to install in sandbox"
    )


class SkillsSubAgentConfig(BaseModel):
    """
    Configuration for a sub-agent with skills support.

    Extends the base SubAgentConfig pattern to include skills allocation.
    """
    name: str = Field(
        ...,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "The name of the sub-agent.",
            }
        },
    )
    description: str = Field(
        ...,
        metadata={
            "x_oap_ui_config": {
                "type": "textarea",
                "description": "The description of the sub-agent for the main agent to decide when to use it.",
            }
        },
    )
    prompt: str = Field(
        default=DEFAULT_SUB_AGENT_PROMPT,
        metadata={
            "x_oap_ui_config": {
                "type": "runbook",
                "description": "The system prompt for the sub-agent.",
                "default": DEFAULT_SUB_AGENT_PROMPT,
            }
        },
    )
    model_name: Optional[str] = Field(
        default="anthropic:claude-sonnet-4-5-20250929",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "anthropic:claude-sonnet-4-5-20250929",
                "description": "Select the AI model for this sub-agent.",
                "options": get_model_options_for_ui(),
            }
        },
    )

    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        optional=True,
        metadata={"x_oap_ui_config": {"type": "mcp"}},
    )
    rag_config: Optional[RagConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "rag",
                "description": "Configure document collections and tools for this sub-agent"
            }
        },
    )

    # Skills for this sub-agent
    skills_config: Optional[SkillsConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "skills",
                "description": "Skills available to this sub-agent"
            }
        },
    )


class GraphConfigPydantic(BaseModel):
    """
    Configuration schema for Skills DeepAgent.

    This configuration includes all options for the skills-enabled agent,
    including model parameters, skills, sandbox settings, and sub-agents.
    """

    template_name: Optional[str] = Field(
        default=GRAPH_NAME,
        metadata={
            "x_oap_ui_config": {
                "type": "agent_name",
                "description": "The name of the agent template.",
            }
        },
    )

    template_description: Optional[str] = Field(
        default=GRAPH_DESCRIPTION,
        metadata={
            "x_oap_ui_config": {
                "type": "agent_description",
                "description": "The description of the agent template.",
            }
        },
    )

    model_name: Optional[str] = Field(
        default="anthropic:claude-sonnet-4-5-20250929",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "anthropic:claude-sonnet-4-5-20250929",
                "description": "Select the AI model to use.",
                "options": get_model_options_for_ui(),
            }
        },
    )

    system_prompt: Optional[str] = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        metadata={
            "x_oap_ui_config": {
                "type": "runbook",
                "placeholder": "Enter a system prompt...",
                "description": "The system prompt to use in all generations.",
                "default": DEFAULT_SYSTEM_PROMPT,
            }
        },
    )

    skills_config: Optional[SkillsConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "skills",
                "title": "Skills",
                "description": "Select skills to enable for this agent"
            }
        },
    )

    sandbox_config: Optional[SandboxConfig] = Field(
        default_factory=SandboxConfig,
        metadata={
            "x_oap_ui_config": {
                "type": "sandbox_config",
                "title": "Sandbox Settings",
                "description": "Configure the E2B sandbox environment"
            }
        },
    )

    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "mcp",
            }
        },
    )

    rag: Optional[RagConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "rag",
            }
        },
    )

    sub_agents: Optional[List[SkillsSubAgentConfig]] = Field(
        default=[],
        metadata={
            "x_oap_ui_config": {
                "type": "agents",
                "mode": "builder",
                "label": "Sub-Agents",
                "description": "Configure sub-agents with their own skills and tools.",
                "default": [],
            }
        },
    )

    include_general_purpose_agent: Optional[bool] = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "label": "Include General-Purpose Agent",
                "description": "Enable the built-in general-purpose sub-agent.",
            }
        },
    )

    recursion_limit: Optional[int] = Field(
        default=DEFAULT_RECURSION_LIMIT,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": DEFAULT_RECURSION_LIMIT,
                "min": 1,
                "max": 1000,
                "description": "The maximum number of steps the agent can take.",
            }
        },
    )
