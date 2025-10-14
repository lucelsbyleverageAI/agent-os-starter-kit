# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agent OS Starter Kit** is a production-ready, multi-user AI agent platform that combines LangGraph agent orchestration, n8n workflow automation, and a comprehensive web interface. It provides authentication, vector knowledge bases, long-term memory, and powerful automation tools in an integrated stack.

## System Architecture

This is a microservices architecture with 7 main components:

### Core Services

1. **LangGraph Backend** (`langgraph/`) - Python/Poetry agent orchestration
   - Defines configurable agent templates (graphs) that users can instantiate
   - Templates: `deepagent`, `tools_agent`, `supervisor_agent`, `deep_research_agent`, `n8n_agent`
   - Runs locally via `langgraph dev` during development (port 2024)
   - Uses MCP for tool integration and Supabase for authentication

2. **LangConnect** (`apps/langconnect/`) - FastAPI data layer
   - RAG knowledge base (ingestion, chunking, vector search)
   - Agent management and permissions APIs
   - Syncs with LangGraph to discover and register agent templates
   - Runs in Docker with hot reload during development (port 8080)

3. **MCP Server** (`apps/mcp/`) - Model Context Protocol gateway
   - Central tool registry surfacing tools to agents
   - OAuth discovery for third-party clients
   - Custom tools defined in `apps/mcp/src/mcp_server/tools/custom_tools.py`
   - Built-in custom tools: Tavily search, E2B code sandbox, Mem0 memory
   - Arcade tool manager defined in `apps/mcp/src/mcp_server/tools/arcade_tools.py` (Arcade is a third party AI tool management platform that handles tool authentication out-of-the-box)
   - Runs in Docker with hot reload (port 8002)

4. **Web Frontend** (`apps/web/`) - Next.js 15 + React 19
   - Chat interface, agent management, knowledge bases, tools playground, memory management
   - Runs locally via `yarn dev` during development (port 3000)
   - Uses Supabase SSR for authentication

5. **Supabase** - Auth + PostgreSQL + Storage stack
   - All authentication flows (JWT-based)
   - Core database with user roles and permissions
   - PGVector extension for knowledge base
   - Studio accessible via Kong gateway (port 8000)

6. **n8n** - Low-code workflow automation (port 5678)
   - 400+ integrations for quick prototyping
   - Agents can be configured to call n8n webhooks

7. **Windmill** - Code-first automation platform (port 9000)
   - Python/TypeScript/Go workflows and tools
   - Separate PostgreSQL instance (port 5433)

### Data Flow

```
User → Web Frontend → Supabase Auth (JWT) → LangGraph Agent
                                         ↓
                              MCP Server (tools) ← LangConnect (RAG/context)
```

## Development Commands

All commands use the Makefile in the root directory:

```bash
# Start complete development stack
make start-dev
# This starts:
# - Docker services (Supabase, LangConnect, MCP, n8n, Windmill)
# - LangGraph dev server (local, port 2024)
# - Web frontend (local, port 3000)

# Stop all services (Docker + background processes)
make stop

# Complete reset (stops services and removes ALL data)
make clean-reset

# Export n8n workflows and credentials to repo
make export-n8n
```

### Individual Service Commands

```bash
# Web Frontend
cd apps/web
yarn dev              # Development server
yarn build            # Production build
yarn lint             # Run linting
yarn lint:fix         # Fix linting issues

# LangGraph (when running standalone)
cd langgraph
poetry install
poetry run langgraph dev --allow-blocking    # Starts on port 2024

# LangConnect (manual testing)
cd apps/langconnect
poetry install
poetry run uvicorn langconnect.server:APP --reload --port 8080

# MCP Server (manual testing)
cd apps/mcp
poetry install
poetry run python -m mcp_server.main --transport http --host 0.0.0.0 --port 8001
```

## Service Endpoints (Local Development)

- **Web Frontend**: http://localhost:3000
- **Supabase Studio**: http://localhost:8000
- **LangGraph API**: http://localhost:2024
- **LangConnect API**: http://localhost:8080 (docs at `/docs`)
- **MCP Server**: http://localhost:8002 (health at `/mcp`)
- **n8n**: http://localhost:5678
- **Windmill**: http://localhost:9000

## Key File Locations

### Configuration
- `.env.local` - All environment variables (created from `.env.local.example`)
- `langgraph/langgraph.json` - Defines agent graph templates and entry points
- `docker-compose.local.dev.yml` - Docker services for local development
- `docker-compose.production.yml` - Production deployment configuration

### Agent Definitions
- `langgraph/src/agent_platform/agents/` - All agent implementations
  - Each agent has: `__init__.py`, `graph.py`, `configuration.py`
  - Graphs are registered in `langgraph.json`

### Database
- `database/migrate.py` - Database migration script
- `supabase/volumes/` - Supabase initialization SQL scripts
- Migration runs automatically via `migration-init` container on startup

### Frontend Structure
- `apps/web/src/app/` - Next.js app router pages
- `apps/web/src/features/` - Feature-specific components (chat, agents, knowledge)
- `apps/web/src/components/` - Shared UI components
- `apps/web/src/lib/` - Utility libraries and API clients
- `apps/web/src/providers/` - React context providers

### API Routes
- `apps/web/src/app/api/langconnect/` - LangConnect proxy routes
- `apps/web/src/app/api/langgraph/` - LangGraph proxy routes
- `apps/web/src/app/api/oap_mcp/` - MCP server proxy
- `apps/web/src/app/auth/` - MCP OAuth endpoints

## Discovery Endpoint Architecture

The platform uses a three-endpoint architecture for agent and assistant discovery. This design provides separation of concerns, independent caching, and admin flexibility.

### The Three Endpoints

1. **Backend: GET /agents/mirror/graphs** (LangConnect)
   - **Purpose**: Returns permission-filtered graph templates (agent types)
   - **Caching**: ETag with 5-minute TTL (graphs change infrequently)
   - **Consumers**:
     - Next.js aggregation proxy (below)
     - Admin UI: `retired-graphs-table.tsx` component (direct call)
   - **Location**: `apps/langconnect/langconnect/api/mirror_apis.py:41`
   - **Why Independent**: Admin UI needs graph lists without assistant data overhead

2. **Backend: GET /agents/mirror/assistants** (LangConnect)
   - **Purpose**: Returns permission-filtered assistant instances
   - **Caching**: ETag with 3-minute TTL (assistants update more frequently)
   - **Consumers**: Next.js aggregation proxy only (internal infrastructure)
   - **Location**: `apps/langconnect/langconnect/api/mirror_apis.py:203`
   - **Why Independent**: Different cache TTL optimized for user-created content

3. **Frontend: GET /api/langconnect/user/accessible-graphs** (Next.js)
   - **Purpose**: Aggregation proxy that combines graphs + assistants
   - **Pattern**: Calls both backend endpoints and merges responses
   - **Consumers**: Web UI components that need both resources
   - **Location**: `apps/web/src/app/api/langconnect/user/accessible-graphs/route.ts:84`
   - **Why Needed**: Convenient single-call API for UI while preserving backend flexibility

### Architecture Benefits

This separation provides several advantages:

1. **Independent Caching**: Graphs (5min) vs Assistants (3min) with separate ETags
2. **Admin Flexibility**: Admin components query graphs directly without assistant overhead
3. **Service Independence**: Microservices can query specific resources independently
4. **Performance**: Parallel backend fetching in proxy reduces overall latency
5. **Separation of Concerns**: Graph templates vs assistant instances are distinct concepts

### Why Not Consolidate?

A single combined endpoint was considered but rejected because:

- **Admin UI Dependency**: `retired-graphs-table.tsx` needs graphs-only queries
- **Different Update Frequencies**: Graphs are templates (stable), assistants are instances (dynamic)
- **Cache Optimization**: Independent versioning enables per-resource cache invalidation
- **Microservice Best Practices**: Resources should be independently queryable

### Endpoint Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Web UI Component                      │
│                  (needs graphs + assistants)                 │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
         ┌────────────────────────────────────┐
         │  Next.js Aggregation Proxy         │
         │  /user/accessible-graphs           │
         └────────┬──────────────┬────────────┘
                  │              │
         ┌────────▼────┐    ┌───▼──────────┐
         │ /mirror/    │    │ /mirror/     │
         │ graphs      │    │ assistants   │
         │ (5min TTL)  │    │ (3min TTL)   │
         └─────────────┘    └──────────────┘
                  ▲              ▲
                  │              │
                  └──────┬───────┘
                         │
              ┌──────────▼──────────┐
              │   Admin UI Direct   │
              │   (graphs only)     │
              └─────────────────────┘
```

### Implementation Details

**Backend Endpoints** (`mirror_apis.py`):
- Use ETag-based HTTP caching with version tracking
- Return 304 Not Modified when client ETag matches
- Filter by user permissions (graph_permissions, assistant_permissions tables)
- Handle retired graphs (hidden from non-admin users)
- Support service account access (see all resources)

**Aggregation Proxy** (`route.ts`):
- Runs on Next.js Edge runtime for low latency
- Calls backend endpoints sequentially (acceptable for UI flows)
- Merges responses into unified discovery payload
- Includes performance timing for debugging
- Passes through user JWT for permission filtering

### Cache Versioning

Both backend endpoints use versioned caching:
- `graphs_version` and `assistants_version` in `langconnect.cache_state` table
- Versions increment on mutations (create/update/delete operations)
- ETags generated from versions: `"graphs-v{version}"`, `"assistants-v{version}"`
- Clients send `If-None-Match` header to enable 304 responses

## Agent System

### How Agents Work

1. **Agent Templates (Graphs)**: Defined in `langgraph/src/agent_platform/agents/`
2. **Registration**: `langgraph.json` maps graph names to Python module paths
3. **Discovery**: LangConnect's sync scheduler periodically discovers available graphs from LangGraph
4. **Instantiation**: Users create agent instances from templates via the web UI
5. **Execution**: Agents run in LangGraph, call tools via MCP, access knowledge via LangConnect

### Adding a New Agent Template

1. Create directory: `langgraph/src/agent_platform/agents/your_agent/`
2. Implement: `graph.py` (with `graph` variable), `configuration.py` (config schema)
3. Register in `langgraph.json`:
   ```json
   "your_agent": "./src/agent_platform/agents/your_agent/graph.py:graph"
   ```
4. Restart LangGraph dev server
5. Click "Initialize Platform" in web UI to discover the new template

### Agent Configuration Schema

Each agent template defines a Pydantic configuration model (subclass of `ConfigurableFieldSpec`) that specifies:
- User-configurable parameters (model selection, temperature, system prompts, etc.)
- Tool permissions and access control
- Knowledge base connections

## Authentication Architecture

### JWT Flow
1. User signs in via Supabase Auth (web frontend)
2. Supabase issues JWT with user ID and roles
3. JWT passed to all backend services via Authorization header
4. Each service validates JWT against Supabase public key
5. Services use JWT claims for user context and permissions

### Service-to-Service Auth
- **LangGraph → MCP**: Uses `MCP_SERVICE_ACCOUNT_KEY` to generate temporary tokens
- **LangConnect → Supabase**: Uses `SUPABASE_SERVICE_KEY` for admin operations
- **Web → All Services**: Proxies user JWT through API routes

### User Roles
- `dev_admin`: Full platform access (first user auto-assigned)
- `authenticated`: Standard user access
- Custom roles can be defined in Supabase

## MCP Server Integration

### Tool Discovery
- Tools are defined in `apps/mcp/src/mcp_server/tools/`
- Base tool class: `apps/mcp/src/mcp_server/tools/base.py`
- Custom tools: `apps/mcp/src/mcp_server/tools/custom_tools.py`
- Arcade tools: Dynamically discovered from Arcade API

### Adding Custom Tools
1. Create tool class in `custom_tools.py` inheriting from `BaseTool`
2. Implement `execute()` method with tool logic
3. Define input schema with Pydantic model
4. Tools are automatically discovered on server startup

### OAuth Discovery Flow
1. Third-party client requests `/.well-known/oauth-authorization-server`
2. MCP server returns OAuth endpoints hosted by web frontend
3. Client redirects user to web frontend for auth
4. Frontend exchanges Supabase JWT for MCP token
5. Client uses MCP token to call MCP server tools

## Hot Reloading in Development

- **LangGraph**: Automatic reload via `langgraph dev`
- **Web Frontend**: Next.js Fast Refresh
- **LangConnect**: uvicorn reload via `UVICORN_RELOAD=true`
- **MCP Server**: uvicorn reload via `UVICORN_RELOAD=true`

Code changes in `langconnect/` and `mcp/src/` directories are automatically detected and trigger reload without restarting Docker containers.

## Database Migrations

The `migration-init` container runs automatically on `make start-dev`:
- Waits for Supabase database to be healthy
- Executes migrations in `database/migrate.py`
- Creates `langconnect` schema and required tables
- Other services depend on `migration-init` completing successfully

To reset schema (⚠️ destroys data):
```bash
MIGRATION_RESET_SCHEMA=true make start-dev
```

## Common Workflows

### First-Time Setup
1. `cp .env.local.example .env.local` and fill in secrets
2. `make start-dev`
3. Create first user in Supabase Studio (http://localhost:8000)
4. Sign in at http://localhost:3000
5. Click "Initialize Platform" on Agents page to discover templates

### Testing MCP Tools
1. Run `npx @modelcontextprotocol/inspector` in separate terminal
2. Connect to `http://localhost:8002/mcp`
3. Complete OAuth flow to authenticate
4. Inspect and test available tools

### Debugging Agent Execution
- Use LangGraph Studio (auto-opens with `langgraph dev`)
- Check Sentry for errors (if configured)
- Review agent logs in LangGraph terminal output
- Check tool execution logs in MCP server output

## Important Notes

- **Do not commit `.env.local`** - contains secrets
- **First user is auto-assigned `dev_admin` role** - manage subsequent users in Supabase Studio
- **LangGraph and Web run locally** (not in Docker) for optimal development experience
- **Docker services share Supabase PostgreSQL** except Windmill (separate DB)
- **n8n workflows are imported** from `n8n/data/` on container startup
- **MCP OAuth requires web frontend running** for authorization flow
