from typing import Optional, List
from pydantic import BaseModel, Field


# System prompts and constants
UNEDITABLE_SYSTEM_PROMPT = """\nYou can invoke sub-agents by calling tools in this format:
`delegate_to_<name>(user_query)`--replacing <name> with the agent's name--
to hand off control. Otherwise, answer the user yourself.

The user will see all messages and tool calls produced in the conversation, 
along with all returned from the sub-agents. With this in mind, ensure you 
never repeat any information already presented to the user.
"""

DEFAULT_SUPERVISOR_PROMPT = """You are a supervisor AI overseeing a team of specialist agents. 
For each incoming user message, decide if it should be handled by one of your agents. 
"""


class AgentsConfig(BaseModel):
    """
    Configuration for individual sub-agents managed by the supervisor.
    
    This configuration defines how to connect to and interact with remote
    agents that the supervisor can delegate tasks to.
    
    Attributes:
        deployment_url: The base URL where the agent is deployed
        agent_id: Unique identifier for the agent in the deployment
        name: Human-readable name for the agent (used in delegation)
        
    Example:
        ```python
        agent_config = AgentsConfig(
            deployment_url="https://agents.example.com",
            agent_id="research-agent-v1",
            name="Research Assistant"
        )
        ```
    """
    deployment_url: str
    """The URL of the LangGraph deployment"""
    
    agent_id: str
    """The ID of the agent to use"""
    
    name: str
    """The name of the agent"""


class GraphConfigPydantic(BaseModel):
    """
    Complete configuration schema for the supervisor agent.
    
    This is the main configuration class that defines all available options
    for the supervisor agent, including sub-agent connections and behavior
    customization.
    
    The configuration includes UI metadata for automatic form generation
    in the agent platform interface.
    
    Attributes:
        agents: List of sub-agents available for delegation
        system_prompt: Custom system instructions for supervision behavior
    """
    
    agents: List[AgentsConfig] = Field(
        default=[],
        metadata={"x_oap_ui_config": {"type": "agents"}},
    )
    """List of sub-agents available for task delegation"""
    
    system_prompt: Optional[str] = Field(
        default=DEFAULT_SUPERVISOR_PROMPT,
        metadata={
            "x_oap_ui_config": {
                "type": "textarea",
                "placeholder": "Enter a system prompt...",
                "description": f"The system prompt to use in all generations. The following prompt will always be included at the end of the system prompt:\n---{UNEDITABLE_SYSTEM_PROMPT}---",
                "default": DEFAULT_SUPERVISOR_PROMPT,
            }
        },
    )
    """Custom system prompt for the supervisor agent""" 