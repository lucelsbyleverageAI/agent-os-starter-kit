import re
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.pregel.remote import RemoteGraph

# Import agent-specific configuration
from agent_platform.agents.supervisor_agent.config import GraphConfigPydantic, AgentsConfig

# Import centralized model utilities
from agent_platform.utils.model_utils import (
    init_model,
    ModelConfig,
    RetryConfig,
)
from agent_platform.utils.prompt_utils import append_datetime_to_prompt

from langgraph_supervisor import create_supervisor

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())



class OAPRemoteGraph(RemoteGraph):
    """
    Custom RemoteGraph implementation with configuration sanitization.
    
    This class extends LangGraph's RemoteGraph to properly handle configuration
    sanitization, ensuring that supervisor-specific configuration doesn't
    interfere with sub-agent configurations.
    """
    
    def _sanitize_config(self, config: RunnableConfig) -> RunnableConfig:
        """
        Sanitize the config to remove non-serializable fields.
        
        This method filters out configuration keys that are specific to the
        supervisor agent to prevent them from being passed to sub-agents,
        which could cause conflicts or unexpected behavior.
        
        Args:
            config: The original configuration from the supervisor
            
        Returns:
            Sanitized configuration safe for sub-agent use
        """
        sanitized = super()._sanitize_config(config)

        # Filter out keys that are already defined in GraphConfigPydantic
        # to avoid the child graph inheriting config from the supervisor
        # (e.g. system_prompt)
        graph_config_fields = set(GraphConfigPydantic.model_fields.keys())

        if "configurable" in sanitized:
            sanitized["configurable"] = {
                k: v
                for k, v in sanitized["configurable"].items()
                if k not in graph_config_fields
            }

        if "metadata" in sanitized:
            sanitized["metadata"] = {
                k: v
                for k, v in sanitized["metadata"].items()
                if k not in graph_config_fields
            }

        return sanitized


def make_child_graphs(cfg: GraphConfigPydantic, access_token: Optional[str] = None):
    """
    Instantiate a list of RemoteGraph nodes based on the configuration.
    
    This function creates remote connections to all configured sub-agents,
    handling authentication and name sanitization for proper delegation.
    
    Args:
        cfg: The configuration for the supervisor graph
        access_token: The Supabase access token for authentication, can be None
        
    Returns:
        A list of RemoteGraph instances ready for delegation
        
    Process:
        1. Validate agent configurations
        2. Sanitize agent names for tool compatibility
        3. Prepare authentication headers
        4. Create RemoteGraph instances for each agent
    """
    
    def sanitize_name(name):
        """
        Sanitize agent names for use in delegation tools.
        
        Converts agent names to valid tool names by:
        - Replacing spaces with underscores
        - Removing disallowed characters (<, >, |, \, /)
        
        Args:
            name: Original agent name
            
        Returns:
            Sanitized name safe for tool usage
        """
        # Replace spaces with underscores
        sanitized = name.replace(" ", "_")
        # Remove any other disallowed characters (<, >, |, \, /)
        sanitized = re.sub(r"[<|\\/>]", "", sanitized)
        return sanitized

    # If no agents in config, return empty list
    if not cfg.agents:
        return []

    # Prepare authentication headers
    headers = {}
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "x-supabase-access-token": access_token,
        }

    def create_remote_graph_wrapper(agent: AgentsConfig):
        """
        Create a RemoteGraph wrapper for a single agent.
        
        Args:
            agent: Agent configuration
            
        Returns:
            Configured OAPRemoteGraph instance
        """
        return OAPRemoteGraph(
            agent.agent_id,
            url=agent.deployment_url,
            name=sanitize_name(agent.name),
            headers=headers,
        )

    # Create RemoteGraph instances for all configured agents
    return [create_remote_graph_wrapper(a) for a in cfg.agents]


def make_model(cfg: GraphConfigPydantic):
    """
    Instantiate the LLM for the supervisor based on the config.
    
    Uses centralized model utilities with production-grade enhancements:
    - Provider-specific optimizations (caching, reasoning)
    - Consistent configuration across all agents
    - No retry wrapper (supervisor uses .bind_tools())
    
    Currently uses GPT-4.1 as the default supervisor model, but this
    could be made configurable in future versions via cfg.
    
    Args:
        cfg: The supervisor configuration
        
    Returns:
        Configured chat model instance without retry wrapper
    """
    # Initialize without retry wrapper to allow .bind_tools() to work
    return init_model(
        ModelConfig(
            model_name="openai/gpt-4.1",
            retry=RetryConfig(max_retries=0),  # Disable retry wrapper for .bind_tools()
        )
    )


def make_prompt(cfg: GraphConfigPydantic):
    """
    Build the system prompt, combining user prompt with delegation instructions.

    Args:
        cfg: The supervisor configuration containing user system prompt

    Returns:
        Complete system prompt with delegation instructions and current datetime
    """
    from agent_platform.agents.supervisor_agent.config import UNEDITABLE_SYSTEM_PROMPT
    base_prompt = cfg.system_prompt + UNEDITABLE_SYSTEM_PROMPT
    return append_datetime_to_prompt(base_prompt)


async def graph(config: RunnableConfig):
    """
    Create and configure the supervisor agent graph.
    
    This function is the main entry point for the supervisor agent. It processes
    the configuration, creates connections to sub-agents, and returns a supervisor
    capable of coordinating multiple specialist agents.
    
    Args:
        config: LangGraph runnable configuration containing:
            - configurable: User configuration parameters
            - metadata: Request metadata (user info, etc.)
            - x-supabase-access-token: Authentication token
            
    Returns:
        A configured supervisor agent ready for execution
        
    Configuration Processing:
        1. Parse and validate configuration using GraphConfigPydantic
        2. Extract authentication tokens from request
        3. Create remote connections to all configured sub-agents
        4. Initialize LLM model for supervisor reasoning
        5. Build system prompt with delegation instructions
        6. Create supervisor with all sub-agents and configuration
        
    Sub-Agent Integration:
        - Remote connections: Established for each configured agent
        - Authentication: Tokens are propagated to sub-agents
        - Delegation: Tools are created with 'delegate_to_' prefix
        - History: Full conversation history is maintained
        
    Error Handling:
        - Missing tokens: Sub-agents are created without authentication
        - Connection errors: Individual agents fail gracefully
        - Configuration errors: Validation provides clear error messages
    """
    
    # Step 1: Parse and validate configuration
    cfg = GraphConfigPydantic(**config.get("configurable", {}))
    
    # Step 2: Extract authentication token for sub-agent communication
    # Try multiple locations where the JWT token might be stored
    supabase_access_token = (
        config.get("configurable", {}).get("x-supabase-access-token") or  # Standard location
        config.get("metadata", {}).get("supabaseAccessToken") or          # Alternative location
        config.get("configurable", {}).get("supabaseAccessToken")         # Another alternative
    )

    # Step 3: Create remote connections to all configured sub-agents
    child_graphs = make_child_graphs(cfg, supabase_access_token)

    # Step 4: Create and return the supervisor
    """
    Supervisor Creation:
    - Coordinates all child graphs (sub-agents)
    - Uses GPT-4o for supervisor reasoning
    - Combines user prompt with delegation instructions
    - Creates delegation tools with 'delegate_to_' prefix
    - Maintains full conversation history
    """
    return create_supervisor(
        child_graphs,
        model=make_model(cfg),
        prompt=make_prompt(cfg),
        config_schema=GraphConfigPydantic,
        handoff_tool_prefix="delegate_to_",
        output_mode="full_history",
    ) 