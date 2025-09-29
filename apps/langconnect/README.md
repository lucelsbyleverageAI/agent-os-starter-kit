# LangConnect

## Overview

LangConnect is the platform’s data and context layer. It serves a dual purpose:

- **AI data plane**: A Postgres + pgvector-backed knowledge store for Retrieval-Augmented Generation (RAG) and structured/metadata retrieval. It handles ingestion, processing, chunking and embeddings for documents and URLs, organising everything into clearly separated collections.
- **Application data layer**: A cohesive API and database for platform concepts such as collections, permissions, agents/assistants, jobs, notifications and public-sharing. It mirrors selected LangGraph state to reduce latency, enrich metadata, and enable sharing and access control within our own application domain.

In short: LangConnect connects our agents to data—internal and external—and prepares that data in the most useful form for context engineering, then exposes it to agents via the MCP server.

---

## Why LangConnect?

- **Purpose-built for AI retrieval**: Store full documents, richly structured metadata, and chunk-level embeddings in Postgres/pgvector for both semantic and metadata-driven retrieval.
- **Extensible ingestion & processing**: Upload files, import URLs and text, perform OCR/table extraction when needed, and chunk intelligently (e.g. markdown-aware).
- **Clear knowledge boundaries**: Collections keep different knowledge domains separate with explicit permissioning (owner/editor/viewer) and optional public links.
- **Mirror layer for LangGraph**: Maintain a local, application-focused view of agents/assistants and execution artefacts. Enrich with our own metadata (e.g. thread names, summaries) and avoid frequent cross-service calls.
- **One API for the app and agents**: The web app uses LangConnect directly; agents access the same data via the MCP server under the user’s context.

---

## High-Level Architecture

- **Postgres + pgvector**: Primary store for collections, documents, chunks, embeddings, jobs and application metadata. Designed for both RAG and traditional/metadata filtering.
- **Processing pipeline**: Asynchronous job system to transform uploads and URLs into clean text, tables and chunks with embeddings, with selectable processing modes.
- **Permissions and sharing**: Per-collection permission levels; public-sharing endpoints for read-only access where appropriate.
- **Mirror of LangGraph**: Selective synchronisation of agents/assistants and related state from the LangGraph service, cached locally for speed and enriched with app-specific metadata.
- **MCP bridge**: Agents obtain user-scoped access to LangConnect via the MCP server, ensuring proper identity and authorisation are enforced for all tool usage.

---

## Key Capabilities

### 1) AI Data Plane (RAG + Structured Retrieval)

- Store documents, URLs and free text as first-class documents in collections.
- Process into chunks with embeddings (pgvector) for semantic search and hybrid strategies.
- Maintain structured metadata (titles, source type, filenames/URLs, word counts, content length, custom tags) enabling precise filtering by collection, source, time, etc.
- Designed to be extended to other knowledge backends (e.g. graph stores) should you wish to project the same data into a graph database (Kùzu or others).

### 2) Application Data Layer

- Collections, permissions and public sharing
- Agents/assistants mirror, notifications and jobs
- Enrichment of LangGraph entities with application-specific metadata (summaries, display names, annotations)
- Caching layer to reduce round-trips to LangGraph for common queries

---

## Document Processing Pipeline

The pipeline turns inputs into high-quality chunks and embeddings suitable for LLM context:

- **Inputs**: File uploads, URLs (including YouTube), and free text.
- **Modes**: `fast` (no OCR, quick path for digital docs), `balanced` (OCR + table extraction, recommended for mixed sources).
- **Features**: OCR for scanned docs, table extraction, figure handling (configurable), markdown-aware chunking, metadata capture.
- **Async jobs**: All heavy processing runs via background jobs with status polling and results retrieval.

Primary routes (abbreviated):

- `POST /collections/{collection_id}/documents` — upload files/URLs/text for processing (async job)
- `POST /collections/{collection_id}/documents/batch` — batch mixed inputs in one job
- `GET  /collections/{collection_id}/documents` — list documents (metadata + counts)
- `GET  /collections/{collection_id}/documents/{document_id}` — document details; optional chunk details
- `DELETE /collections/{collection_id}/documents/{document_id}` — delete a document and its chunks
- `POST /documents/extract/text` — lightweight text extraction (file or URL) for chat workflows (async)

Related endpoints exist for chunks/semantic search, collections management, jobs and notifications.

---

## Authentication and Authorisation

LangConnect supports two credential types via `Authorization: Bearer <token>`:

- **User (Supabase JWT)**: Standard end-user identity. Used by the web app and by agents acting on behalf of a user. Grants access to the user’s collections and data based on permissions.
- **Service Account (`LANGCONNECT_SERVICE_ACCOUNT_KEY`)**: For automated back-end flows (e.g. ETL, synchronisers). Service accounts are privileged but must attribute ownership appropriately when creating content. Some user-scoped tools (e.g. personal memory) remain user-only.

How agents get access via MCP:

1. Frontend or LangGraph exchanges a user’s Supabase JWT for an MCP Access Token (signed with the shared secret).
2. Agents call the MCP server with that token.
3. MCP validates and forwards requests to LangConnect under the user’s identity, enforcing permissions and data isolation.

Notes:

- CORS is controlled via `ALLOW_ORIGINS`.
- Optional Sentry initialisation captures errors and breadcrumbs when DSNs are provided.

---

## Using LangConnect

### From the Web Frontend

- Create and manage collections.
- Upload documents, import URLs, and monitor processing jobs.
- Browse, search and filter documents and chunks; manage sharing and permissions.

### From Back-end/Integrations

- Use the service account key to ingest or synchronise external systems (e.g. SharePoint, file stores) into LangConnect collections.
- For custom knowledge graphs or RAG spaces, project external data into LangConnect (and optionally into a graph DB) to keep a secure, local substrate for agents.
- Alternatively, expose external systems as direct tools via MCP for on-demand access without ingestion. Choose ingestion vs. direct tooling per use case.

---

## API Surface (Selected)

Routers included in the app:

- `collections` — create/list/update/delete collections, permissions, public sharing
- `documents` — upload/import/list/get/delete documents; batch operations; text extraction
- `chunks` — chunk/embedding search and retrieval
- `users` — user-related helpers
- `agents` — mirror endpoints for agent/assistant metadata
- `jobs` — submit and track processing jobs
- `notifications` — in-app notifications
- `public_permissions` — public link sharing & access checks
- `memory` — memory-context related routes used by MCP/agents
- `gcp_images` — optional GCP object storage helpers (behind `IMAGE_STORAGE_ENABLED`)

Explore the FastAPI docs at `/docs` or `/redoc` when the server is running.

---

## Configuration

Environment variables (selected):

- Supabase: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- Service account: `LANGCONNECT_SERVICE_ACCOUNT_KEY`
- Postgres: `LANGCONNECT_POSTGRES_HOST`, `LANGCONNECT_POSTGRES_PORT`, `LANGCONNECT_POSTGRES_USER`, `LANGCONNECT_POSTGRES_PASSWORD`, `LANGCONNECT_POSTGRES_DB`, `LANGCONNECT_POSTGRES_SCHEMA`
- CORS: `ALLOW_ORIGINS` (JSON array string), defaults to `"http://localhost:3000"`
- Embeddings: OpenAI embeddings are used by default in non-test environments
- Testing: `IS_TESTING=true` enables deterministic fake embeddings and relaxed auth helpers for tests
- Optional: `IMAGE_STORAGE_ENABLED=true` to expose GCP image endpoints (requires appropriate GCP credentials in the environment)

Refer to the Docker Compose and root environment files for the full list used in development.

---

## Local Development

### Recommended (full stack)

Run everything from the repository root so that all services (Supabase, MCP, LangGraph, web app, LangConnect, etc.) start together with the correct wiring:

```bash
make start-dev
```

This uses Docker for infrastructure and hot-reloads app services for a smooth developer experience. See `scripts/README.md` for details and troubleshooting.

### Standalone (LangConnect only)

You can run LangConnect by itself if you provide the required environment variables (not recommended for typical workflows):

```bash
cd apps/langconnect
poetry install
poetry run uvicorn langconnect.server:APP --reload --host 0.0.0.0 --port 8080
# or
poetry run python -m langconnect
```

Health check:

```bash
curl http://localhost:8080/health
```

Open the interactive API docs at `http://localhost:8080/docs`.

---

## Extending LangConnect

- **New sources**: Add importers for additional repositories (e.g. SharePoint, Google Drive). Decide ingestion vs. on-demand tool access.
- **Custom chunking & embeddings**: Swap chunking strategies and embeddings; add hybrid search strategies.
- **Graph projection**: Mirror selected collections into a graph database for relationship-first retrieval whilst retaining pgvector for semantic search.
- **Metadata enrichment**: Attach summaries, tags, owners and domain-specific annotations to collections/documents for powerful filtering.

---

## Observability & Ops

- **Sentry**: Optional initialisation captures errors and breadcrumbs.
- **Health**: `/health` endpoint indicates readiness.
- **Jobs**: Processing runs asynchronously; use jobs endpoints to track progress and collect results.

---

## Summary

LangConnect is the connective tissue between agents and data. It standardises ingestion, processing and retrieval, enforces permissions, mirrors key LangGraph state for speed, and exposes a clean API that both the application and agents (via MCP) can rely on.


