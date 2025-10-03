from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel
from typing import Any, Optional, List
from typing_extensions import TypedDict, NotRequired


class RagConfig(BaseModel):
    langconnect_api_url: Optional[str] = None
    collections: Optional[List[str]] = None


class MCPConfig(BaseModel):
    url: Optional[str] = None
    tools: Optional[List[str]] = None


class SerializableSubAgent(BaseModel):
    name: str
    description: str
    prompt: str
    model_name: Optional[str] = None  # New centralized model config (string model name)
    model: Optional[dict[str, Any]] = None  # Legacy model config (kept for backward compatibility)
    mcp_config: Optional[MCPConfig] = None
    rag_config: Optional[RagConfig] = None
    tools: Optional[list[str]] = None


def create_configurable_agent(
    default_instructions: str,
    default_sub_agents: list[SerializableSubAgent],
    tools,
    agent_config: Optional[dict] = None,
    **kwargs,
):
    tools = [t if isinstance(t, BaseTool) else tool(t) for t in tools]
    tool_names = [t.name for t in tools]

    class AgentConfig(BaseModel):
        instructions: str = default_instructions
        subagents: list[SerializableSubAgent] = default_sub_agents
        tools: list[str] = tool_names

    def build_agent(config: Optional[dict] = None):
        # Import here to avoid circular import at module load time
        try:
            from .graph import create_deep_agent
        except ImportError:
            from agent_platform.agents.deepagents.graph import create_deep_agent

        if config is not None:
            config_from_runnable = config.get("configurable", {})
            # This is a hack to get the full config for sub-agent tool loading
            kwargs["runnable_config"] = config
        else:
            config_from_runnable = {}

        config_fields = {
            k: v
            for k, v in config_from_runnable.items()
            if k in ["instructions", "subagents"]
        }
        parsed_config = AgentConfig(**config_fields)
        return create_deep_agent(
            instructions=parsed_config.instructions,
            tools=[t for t in tools if t.name in parsed_config.tools],
            subagents=parsed_config.subagents,
            config_schema=AgentConfig,
            **kwargs,
        ).with_config(agent_config or {})

    return build_agent


def async_create_configurable_agent(
    default_instructions: str,
    default_sub_agents: list[SerializableSubAgent],
    tools,
    agent_config: Optional[dict] = None,
    **kwargs,
):
    tools = [t if isinstance(t, BaseTool) else tool(t) for t in tools]
    tool_names = [t.name for t in tools]

    class AgentConfig(BaseModel):
        instructions: str = default_instructions
        subagents: list[SerializableSubAgent] = default_sub_agents
        tools: list[str] = tool_names

    def build_agent(config: Optional[dict] = None):
        # Import here to avoid circular import at module load time
        try:
            from .graph import async_create_deep_agent
        except ImportError:
            from agent_platform.agents.deepagents.graph import async_create_deep_agent

        if config is not None:
            config_from_runnable = config.get("configurable", {})
            # This is a hack to get the full config for sub-agent tool loading
            kwargs["runnable_config"] = config
        else:
            config_from_runnable = {}

        config_fields = {
            k: v
            for k, v in config_from_runnable.items()
            if k in ["instructions", "subagents"]
        }
        parsed_config = AgentConfig(**config_fields)
        return async_create_deep_agent(
            instructions=parsed_config.instructions,
            tools=[t for t in tools if t.name in parsed_config.tools],
            subagents=parsed_config.subagents,
            config_schema=AgentConfig,
            **kwargs,
        ).with_config(agent_config or {"recursion_limit": 1000})

    return build_agent