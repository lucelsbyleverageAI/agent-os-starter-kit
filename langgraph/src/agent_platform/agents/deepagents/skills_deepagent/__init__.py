"""
Skills DeepAgent - An agent template with E2B sandbox and skills support.

This agent extends the basic DeepAgent with:
- Built-in E2B filesystem tool for sandbox operations
- Skills loading system (metadata in system prompt, files in sandbox)
- Shared filesystem architecture for inter-agent communication
"""

from .graph import graph
from .configuration import GraphConfigPydantic

__all__ = ["graph", "GraphConfigPydantic"]
