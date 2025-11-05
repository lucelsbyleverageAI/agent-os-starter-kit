# Web Frontend

## Overview

The web application is the primary user interface for the AI Agent Operating System. It provides a secure, feature-rich, and highly responsive environment for users to interact with the platform's capabilities, including managing agents, engaging in real-time chat, curating knowledge bases, and testing tools.

Built with Next.js and TypeScript, it is architected as a modern, feature-driven application that also serves as a secure gateway—a **Backend for Frontend (BFF)**—for all client-side interactions with the downstream services.

---

## High-Level Architecture

The web app is a standalone Next.js application that communicates with the platform's backend services via a series of secure API proxies.

-   **Technology**: Next.js (with App Router), TypeScript, Tailwind CSS, and shadcn/ui for the component library.
-   **Architecture**: The codebase is organised into a feature-driven structure, with core business logic and UI components encapsulated in dedicated directories (`src/features`, `src/providers`, `src/hooks`).
-   **Backend for Frontend (BFF)**: The Next.js server acts as a secure API gateway. Instead of making direct calls to downstream services from the browser, the client-side code calls API routes within the Next.js app (`/api/...`), which then proxy the requests to the appropriate backend service (`langconnect`, `langgraph`, `mcp`). This is a crucial security pattern that prevents sensitive credentials like API keys from ever being exposed to the client.

---

## Key Capabilities

-   **Authentication**: A complete authentication experience using Supabase, including an invitation-only registration flow and a full OAuth 2.1 implementation that allows third-party clients to securely connect to the platform.
-   **Agent Management**: A comprehensive interface for users to browse agent templates, create and configure new agent instances, manage permissions, and view all their available agents in a central dashboard.
-   **Real-time Chat**: A sophisticated, real-time chat interface powered by the LangGraph SDK, providing a seamless, streaming experience for interacting with agents.
-   **Knowledge Base Management**: A full-featured UI for creating and managing knowledge base "collections." It includes a high-performance batch upload system that can process files, URLs, and raw text to be used for Retrieval-Augmented Generation (RAG).
-   **Developer Tools**: Includes a **Tool Playground** for inspecting the input schemas of all available MCP tools and executing them in a controlled environment to test their functionality.
-   **Administration**: A dedicated interface for `dev_admin` users to perform platform-level initialization and configuration tasks.

---

## Advanced Architectural Patterns

To deliver a highly responsive and robust user experience, the web application employs several advanced architectural patterns:

-   **Data Mirroring**: For performance-critical features like the agent dashboard and thread history sidebar, the UI reads data from a high-speed "mirror" in the `langconnect` service rather than making slow, direct queries to the LangGraph service.
-   **Multi-Layered Caching**: It uses a sophisticated caching strategy that combines long-lived caches for static data (e.g., agent templates) with shorter-lived, "stale-while-revalidate" caches for more dynamic data (e.g., knowledge base collections).
-   **Version-Aware Invalidation**: The agent caching system is "version-aware." It periodically polls the backend to check for data updates and automatically invalidates its local cache when the underlying data has changed, ensuring a high degree of data consistency without constant re-fetching.

---

## Configuration

The web application is configured via environment variables. For a complete list, see the `.env.example` file. Key variables include:

-   `NEXT_PUBLIC_SUPABASE_URL` & `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Required for connecting to your Supabase instance.
-   `NEXT_PUBLIC_BASE_API_URL`: The root URL for the `langconnect` service.
-   `NEXT_PUBLIC_MCP_SERVER_URL`: The public URL for the MCP server.

---

## Local Development

The web app is designed to be run as part of the complete platform stack.

### Recommended Method (Full Stack)

The best way to run the web app for development is by using the orchestration scripts in the root of the repository. This ensures all backend services and dependencies are available and correctly configured.

From the project root, run:
```bash
make start-dev
```

This will start the web application's development server on `http://localhost:3000` with hot-reloading enabled. For more details, see the main `scripts/README.md`.

### Standalone Method

You can run the web app as a standalone service, but you will need to ensure that all backend services (`langconnect`, `mcp`, etc.) are running and that the environment variables in your `.env.local` file are correctly pointing to them.

From the `apps/web` directory, run:
```bash
# 1. Install dependencies
yarn install

# 2. Run the development server
yarn dev
```
