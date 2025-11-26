"""
Skills DeepAgent - An agent template with E2B sandbox and skills support.

This agent uses a sandbox-only architecture with:
- execute_in_sandbox tool for ALL file operations (no state filesystem)
- Skills loading system (metadata in system prompt, files in sandbox)
- Shared filesystem architecture for inter-agent communication
- Sub-agents with full sandbox access
"""

try:
    from .graph import graph
    from .configuration import GraphConfigPydantic
except ImportError:
    from agent_platform.agents.deepagents.skills_deepagent.graph import graph
    from agent_platform.agents.deepagents.skills_deepagent.configuration import GraphConfigPydantic

__all__ = ["graph", "GraphConfigPydantic"]
