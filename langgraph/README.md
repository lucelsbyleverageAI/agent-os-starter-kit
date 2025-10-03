# Agent OS - Langgraph

## Overview

LangGraph is the core agent orchestration framework within the Agent Operating System stack. It is responsible for defining, configuring, and running AI agents that interact with other services such as the Langconnect backend, the MCP tools server, and the web frontend. LangGraph provides a flexible, extensible foundation for building, deploying, and managing agents, with a strong focus on configuration, modularity, and integration.

At a high level, LangGraph produces configurable graphs (or agent templates). You can parameterise these graphs with system prompts, model choices, enabled tools, MCP access configuration, RAG collections, and other execution knobs. From those graphs, the platform creates assistants (versioned, user-configured instances) that users interact with in the UI and via APIs.

---

## Why LangGraph?

LangGraph is our chosen agent framework for several key reasons:

- **Excellent Local Developer Experience**: LangGraph is open source and can be run entirely locally, allowing rapid prototyping and testing of agents using a simple CLI. Developers can iterate quickly without any cloud dependencies.
- **Built-in Agent Debugging**: When paired with LangSmith (a commercial add-on), LangGraph offers advanced debugging, tracing, and analytics for agent workflows. However, all core features work locally without LangSmith.
- **Seamless Scaling and Deployment**: When deployed via the commercial LangGraph platform, scaling, versioning, and orchestration of agents are handled automatically. The platform exposes a comprehensive API for creating, versioning, running, and streaming agents.
- **Open Source and Self-Hostable**: The core codebase is open source and can be self-hosted, with generous limits for local and small-scale deployments. Commercial features (LangSmith, hosted LangGraph) are available for larger-scale or production use.
- **Unified API and Integration**: LangGraph’s API makes it easy to integrate with our frontend and other backend services, supporting both local and cloud deployments with minimal code changes.

This combination of local-first development, powerful debugging, and production-grade deployment is why LangGraph is at the heart of our agent OS.

---

## High-Level Architecture

This langgraph template is an adapted version of LangGraph's [pen Agent Platform](https://github.com/langchain-ai/open-agent-platform) - see [Full Documentation Site Here](https://docs.langchain.com/labs/oap)

LangGraph operates as a standalone service, but is tightly integrated with the rest of the platform:

- **Frontend (Web)**: Users interact with agents via our frontend web interface, which communicates with LangGraph’s API to list, configure, and run agents (called "assistants" when instantiated). We also use LangConnect as a middle layer for managing user permissions.
- **LangConnect**: Agents can retrieve and process documents using the RAG backend for advanced retrieval-augmented generation.
- **MCP Server (Tools)**: Agents can access external tools and services via the MCP protocol, enabling rich tool-augmented workflows. Generally, tools, contexts, and integrations are defined in the MCP server for best practice, but some tools (e.g., those for interacting with LangGraph’s internal state) may be defined directly within LangGraph.
- **Supabase**: Used for authentication and persistent storage of user and assistant data.

LangGraph exposes an API for:
- Listing available agents and their configurations
- Creating and managing assistant instances (user-configured agent versions)
- Running and streaming agent executions
- Managing agent templates and their metadata

### How LangGraph fits into the wider stack

- LangGraph orchestrates agent logic and delegates tool execution to the MCP Server.
- MCP mediates access to both internal services (LangConnect for RAG/memory) and external providers (search, extraction, etc.).
- The Web frontend manages user sessions and presents a UI to configure assistants and invoke agents; it calls LangGraph’s API and visualises outputs/streams.
- Supabase provides the single source of truth for end-user identity. Service-to-service automation uses service accounts.

---

## Directory Structure

- **agents/**: Contains individual agent templates. Each agent is defined as a template with its own configuration schema (config), state management (state), and execution graph (graph). Agents are dynamically loaded and can be extended or replaced without changing the core platform.

### n8n Agent Bridge

- Located at `src/agent_platform/agents/n8n_agent/`.
- Config: `GraphConfigPydantic` with a single field `webhook_url`.
- Graph: forwards `{thread_id, user_message}` to n8n and streams back chunks.
- The bridge filters n8n metadata and emits custom stream events consumed by the web UI for live rendering.
- **services/**: Shared services used by multiple agents, such as authentication, logging, or external integrations.
- **types/**: Common type definitions used throughout the platform, ensuring consistency and type safety.
- **utils/**: Utility functions and helpers shared across agents and services.

---

## Agent Configuration and Metadata

Each agent defines a **config object**. This object describes all configurable parameters for the agent, including types, defaults, and metadata. The frontend (via the `oap-ui-config` metadata) uses this schema to dynamically render configuration forms, allowing users to customise agent behaviour without code changes.

- **Config**: Defines what users can change (e.g., model, temperature, tool access).
- **State**: Tracks the runtime state of an agent during execution.
- **Graph**: Encapsulates the agent’s logic, workflow, and tool usage.

From these graphs, the system creates **Assistants**: parameterised, versioned instances that users interact with. Assistants are the unit of execution in the UI and API.

---

## Centralised Model Configuration

To ensure consistency, maintainability, and production-readiness, the platform uses a centralised model configuration system located in `src/agent_platform/utils/model_utils.py`. This module is the single source of truth for all LLM configurations and provides numerous benefits:
- **Easy Maintenance**: Update the model registry once, and all agents automatically get access to new models.
- **Production-Grade Features**: Automatic retry and fallback logic for all models.
- **Provider Optimisations**: Centralised handling of provider-specific features like Anthropic prompt caching and OpenAI reasoning models.
- **Consistency**: All agents use the same configuration and initialisation logic.

### The Model Registry

The core of the system is the `MODEL_REGISTRY`, which defines all available models, their capabilities, tiers (e.g., Fast, Standard, Advanced), context windows, and other metadata. This registry drives the model selection in the UI and the behaviour of the models at runtime.

### How to Use in New Agents

All new agents **must** use this centralised system for model configuration and initialisation.

#### 1. Agent Configuration (`config.py`)

In your agent's configuration file, use the `get_model_options_for_ui()` utility to dynamically populate the model selection dropdown. This ensures that when the central registry is updated, your agent's UI will automatically display the new models.

**Example from `tools_agent/config.py`**:
```python
from agent_platform.utils.model_utils import get_model_options_for_ui

class GraphConfigPydantic(BaseModel):
    model_name: Optional[str] = Field(
        default="anthropic:claude-sonnet-4-5-20250929",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "description": "Select the AI model to use.",
                "options": get_model_options_for_ui(),  # Dynamically populated!
            }
        },
    )
    # ... other config fields
```

#### 2. Model Initialisation (`graph.py`)

In your agent's graph file, use `init_model_simple()` to initialise the model. This helper function takes care of applying all production-grade features like retry logic, streaming support, and provider-specific optimisations based on the model's entry in the registry.

**Example from `tools_agent/graph.py`**:
```python
from agent_platform.utils.model_utils import init_model_simple

# Inside your graph builder function
def graph(config: GraphConfig):
    # ...
    model = init_model_simple(
        model_name=config.configurable.get("model_name"),
    )
    # ... now use the model to build your agent
```
This replaces older patterns of using `init_chat_model()` or instantiating a `ChatModel` class directly.

#### 3. Message Trimming (Recommended)

To prevent context window errors, it is highly recommended to use the built-in message trimming functionality. You can create a `pre_model_hook` to automatically trim the message history before each call to the LLM.

```python
from agent_platform.utils.model_utils import (
    create_trimming_hook,
    MessageTrimmingConfig,
)

# Create the trimming hook
trimming_hook = create_trimming_hook(
    MessageTrimmingConfig(
        max_tokens=100000, # Conservative limit
        strategy="last",
    )
)

# Use it when creating your agent
agent = create_react_agent(
    model=model,
    tools=tools,
    pre_model_hook=trimming_hook,
)
```

For more detailed information on advanced configuration, fallbacks, provider-specific features, and more, please refer to the full documentation: `src/agent_platform/utils/MODEL_UTILS_README.md`.

---

## Authentication Model

LangGraph participates in the platform’s unified authentication model:

- End users authenticate with Supabase (JWT). The frontend forwards the JWT to LangGraph where it is validated (`src/agent_platform/services/auth.py`).
- When an agent calls tools, LangGraph fetches auth data via `fetch_tokens` (`src/agent_platform/services/mcp_token.py`):
  - If a Supabase JWT is present, it is used directly as `Authorization: Bearer <jwt>` to the MCP server for user-scoped interactions.
  - If no user context is present (e.g., API-key automation), LangGraph uses `MCP_SERVICE_ACCOUNT_KEY` to call MCP as a `service_account`.
- MCP enforces that memory tools require end-user context. Service accounts cannot access memory tools unless they provide user context.

### User vs. Service Account Identities & API Key Usage

- **User (Supabase JWT)**: Represents an end-user with a valid Supabase JSON Web Token. When a user creates a thread, their user ID is saved as `metadata.owner`. This ensures that all subsequent operations on that thread are restricted to the owner, providing data isolation. Calls made with a JWT can access user-scoped tools like memory.

- **Service Account (`x-api-key`)**: Represents automated processes or backend services using a static API key. When a request is made with an API key, the identity is authenticated as `"service_account"`. 
  - Threads created this way are owned by `"service_account"`.
  - **Crucially, service accounts cannot access user-scoped tools like memory.** The MCP server requires a valid user JWT to be forwarded to the underlying memory service (LangConnect), and this is not available in the service account flow. Any attempt by a service account to use a memory tool will fail.

---

## Logging

Sentry logging is centralised in `src/agent_platform/sentry.py`. It initialises automatically on package import and captures ERROR-level events; INFO-level logs are breadcrumbs.

---

## Defining New Agents

To define a new agent:

1. **Create a Template**: Add a new directory in `agents/` with the agent’s config, state, and graph modules.
2. **Define Config**: Specify the agent’s configuration schema, including all user-adjustable parameters and their metadata for the frontend.
3. **Implement State and Graph**: Implement the agent’s runtime state and execution logic.
4. **Register the Agent**: Add the agent to `langgraph.json` to make it available on the platform.
5. **Test Locally**: Use the CLI to run and debug the agent locally, with or without LangSmith.
6. **Frontend Integration**: New agents will automatically register in the frontend once initialised, but you may want to create custom tool components or special treatment in the frontend for better UX.
7. **Deploy**: When ready, deploy to the LangGraph platform for production use, benefiting from automatic scaling and API exposure.

Best practices:
- Logging: use `agent_platform.sentry.get_logger(__name__)` and rely on Sentry to capture exceptions.
- Authentication: validate users via `services/auth.py`; acquire tool auth via `services/mcp_token.fetch_tokens`.
- MCP and RAG tools: build tools using helpers in `utils/tool_utils.py`, e.g. `create_langchain_mcp_tool_with_universal_context`, `create_rag_tool_with_universal_context`, and wrappers like `wrap_mcp_authenticate_tool`.


---

## Local Development Instructions

1. **Copy Environment File**

   Copy the example environment file to set up your local environment variables:

   ```bash
   cp .env.example .env.local
   ```

2. **Install Dependencies**

   Use Poetry for Python dependency management:

   ```bash
   poetry install
   ```

3. **Start the Local Server**

   Run the LangGraph development server locally (with blocking allowed for debugging):

   ```bash
   poetry run langgraph dev --allow-blocking
   ```

   This will start the API server and allow you to interact with your agents locally.

   Note: Because LangGraph relies on other services (MCP server, LangConnect, Supabase) for authentication and tools, the recommended workflow is to run the full stack from the repository root (Docker Compose/local scripts). Running LangGraph alone will require careful configuration of environment variables (e.g., `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `MCP_SERVICE_ACCOUNT_KEY`, `SENTRY_DSN_LANGGRAPH`) and working service endpoints.

---

See the root README for full development and deployment instructions.
