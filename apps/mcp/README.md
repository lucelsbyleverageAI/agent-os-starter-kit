# MCP Server

The MCP (Model-Controller-Peripheral) server is the central nervous system for tool usage within the AI platform. Its primary goal is to act as a secure, authenticated, and auditable gateway that exposes tools—both internal business logic and external third-party services—to AI agents.

It ensures that any action an agent takes is explicitly authorised and performed on behalf of a clearly identified entity, either a specific user or a designated service account. This allows for fine-grained, user-scoped authorisation, and ensures users can securely access tools even when using third-party clients, so long as that access is authorised.

## How the MCP Server Works

The MCP server acts as a secure gateway between AI agents and various tools and services. It supports modern MCP clients with robust authentication and authorization.

### Key Principles

-   **Centralised Authentication:** All tool use is guarded by a single, robust authentication layer, ensuring no tool can be used anonymously.
-   **User-Scoped Authorisation:** The server is designed to understand *who* is making the request. It can differentiate between a request made on behalf of "user A" versus "user B" or a "service account". This allows for fine-grained permissions.
-   **Interoperability:** It provides a unified protocol for tool usage, allowing different types of clients—internal LangGraph agents, the web frontend, and even third-party clients like Anthropic's Claude—to access the same set of tools in a standardised way.

### Surfacing and Managing Tools

The MCP server dynamically discovers and surfaces a catalogue of available tools to agents.

#### Custom Business Tools

You can define your own Python-based tools in `src/mcp_server/tools/custom_tools.py`. This is ideal for encapsulating business logic or wrapping APIs. For example, you could create a tool to `query_sales_database` that uses a shared, securely stored API key. These tools are available to any authenticated user or service account with the appropriate permissions.

#### Arcade for User-Authenticated Tools

The integration with Arcade (`src/mcp_server/tools/arcade_tools.py`) provides tools that act on a *user's personal data*, introducing a second layer of authentication:

1.  **Initial Authentication:** The user first authenticates into the MCP server as themselves.
2.  **Service-Specific OAuth:** When the user attempts to use a tool like `send_gmail_email` for the first time, the server detects they haven't authorised access to their Google account and raises an `AuthorizationError`.
3.  **Authorisation Prompt:** The server returns a response containing a unique `auth_url`, prompting the user to go through the OAuth flow to grant the application access to their Gmail, Google Calendar, Microsoft account, etc. Once this is complete, Arcade securely stores the user's token, and subsequent calls succeed.

This dual-authentication model is critical for securely granting agents access to a user's personal accounts without compromising credentials.

### Connecting to Various Clients

The MCP server is designed to be highly accessible and supports multiple connection methods.

-   **Frontend and LangGraph Agents:** The primary clients are the web frontend and your LangGraph agents. They authenticate using a short-lived, JWT-based **MCP Access Token**. This token is purpose-built for accessing the MCP server and encapsulates the user's identity.
-   **Third-Party Clients (e.g., Claude, MCP Inspector):** The server supports modern standards for third-party integration. It exposes OAuth 2.1 discovery endpoints, allowing external applications to programmatically discover how to authenticate and get an MCP Access Token on a user's behalf through a standard authorisation code flow.

## Authentication Flows Explained

Authentication is the cornerstone of the MCP server's security model. The logic, primarily defined in `src/mcp_server/auth/user_context.py`, is built to handle several distinct scenarios, all revolving around two valid credential types: an **MCP Access Token** for user-delegated actions and a **Service Account Key** for automated processes.

All protected routes expect an `Authorization: Bearer <token>` header.

### 1. User on Frontend → MCP Server

This flow covers direct tool usage from the web UI (e.g., a tool playground).

-   **Flow:**
    1.  A user logs into the Next.js frontend using Supabase, which provides a Supabase JWT.
    2.  To interact with a tool, the frontend sends this Supabase JWT to its own backend API route (`/auth/mcp-token`).
    3.  This route validates the Supabase JWT and "exchanges" it for a newly minted **MCP Access Token**, signed with the shared `MCP_TOKEN_SIGNING_SECRET`.
    4.  The frontend makes the call to the MCP server, passing the `mcp_access_token` in the `Authorization: Bearer` header.
    5.  The MCP server validates the MCP token's signature and expiry, establishing the user's context for the request.
-   **Unauthorised Scenario:** If the token is missing, expired, or invalid, the MCP server immediately returns a `401 Unauthorized` error with a `WWW-Authenticate` header, instructing the client on how to get a valid token.

### 2. User on Frontend → LangGraph Agent → MCP Server (On User's Behalf)

This is the most common and powerful flow for agentic actions.

-   **Flow:**
    1.  The user is logged into the frontend and has a Supabase JWT.
    2.  The user sends a message to a LangGraph agent. The frontend passes the user's Supabase JWT with the request to the LangGraph platform.
    3.  The agent decides it needs to use a tool. The LangGraph service uses the user's Supabase JWT to perform an **RFC 8693 Token Exchange** with the frontend's `/auth/mcp-token` endpoint, swapping the Supabase JWT for an **MCP Access Token**.
    4.  The LangGraph agent calls the MCP server with this MCP Access Token.
    5.  The MCP server validates the token and sees that the agent is acting on behalf of a specific user. This ensures the agent only accesses data and tools permitted for that user.
-   **Unauthorised Scenario:** If LangGraph's token exchange fails or it presents an invalid token, the MCP server will reject the request with a `401 Unauthorized`.

### 3. Service Account → MCP Server (User Impersonation)

This flow is for automated processes that need to act on behalf of specific users (e.g., n8n workflows, Zapier automations).

-   **Flow:**
    1.  A system (e.g., n8n workflow) has the `MCP_SERVICE_ACCOUNT_KEY`.
    2.  It makes a direct API call to the MCP server with `Authorization: Bearer <mcp_service_account_key>`.
    3.  The MCP server identifies the key as a service account key and establishes a service account context.
    4.  For user-scoped operations (like memory tools), the system **must include a `user_id` in the request body** to specify which user the operation is for.
    5.  The tool is executed on behalf of the specified user. The service account essentially "impersonates" the user for that specific operation.
-   **Unauthorised Scenario:** If the service account key is incorrect, the server returns a `401 Unauthorized`. If a user-scoped tool is called without a `user_id`, it returns a `400 Bad Request`.

### 4. Service Account → LangGraph Agent → MCP Server (User Impersonation)

This is for triggering agents via an API on behalf of specific users (e.g., n8n workflows triggering LangGraph agents).

-   **Flow:**
    1.  An external system (e.g., n8n) calls a LangGraph agent webhook, authenticating with a LangGraph-level API key and providing a `user_id` in the configuration.
    2.  LangGraph identifies this as a service account request but knows which user it's acting for.
    3.  When the agent needs to use a user-scoped tool (like memory), it passes the `user_id` along with the tool call.
    4.  It calls the MCP server with the service account key and the `user_id` parameter, following the user impersonation flow.
-   **Unauthorised Scenario:** An invalid service account key results in a `401 Unauthorized`. Missing `user_id` for user-scoped tools results in a `400 Bad Request`.

### 5. Third-Party Client → MCP Server

This flow enables external applications (e.g., Claude.ai) to use your platform's tools on behalf of a user.

-   **Flow:**
    1.  The client discovers the platform's OAuth endpoints via the `/.well-known/oauth-authorization-server` metadata URL.
    2.  It initiates a standard OAuth 2.1 Authorization Code flow, redirecting the user to your frontend to log in and approve the connection.
    3.  Upon approval, the client receives an authorisation code, which it exchanges at your frontend's `/auth/mcp-token` endpoint for a fresh **MCP Access Token**.
    4.  The client can now use this token to make authenticated calls to the MCP server on the user's behalf.
-   **Unauthorised Scenario:** Any deviation from the OAuth flow or presentation of an invalid token will result in a `401 Unauthorized` error, with the `WWW-Authenticate` header guiding the client on how to re-authenticate correctly.

## Configuration and Development

### Configuration

The server's behaviour can be configured using environment variables.

#### Arcade Tools (Optional)

Arcade is a commercial service that provides a suite of pre-built, user-authenticated tools. It is free for local development, but has commercial pricing as you expand to more users, which is why it is optional.

-   **`ENABLE_ARCADE`**: Set to `true` to enable the Arcade tools integration.
-   **`ENABLED_ARCADE_SERVICES`**: A comma-separated list of the specific Arcade services you want to enable (e.g., `gmail,google,microsoft,github,asana`). The services you enable will depend on your business use case.

Even without Arcade, you can define your own powerful, self-hosted tools.

#### Custom Tools

The server is designed to be extended with your own custom tools, which is completely free. This is ideal for internal business logic or wrapping proprietary APIs.

### Adding Custom Tools

To add a new tool, you can follow the structure in `src/mcp_server/tools/custom_tools.py`. To be correctly discovered by the server and surfaced to the frontend and agents, each tool should be defined with:

-   A `toolkit_name`
-   A unique `name` for the tool
-   A clear `description` of what it does
-   The required `parameters` defined in a schema

### Local Development

While the MCP server can be run as a standalone service, it relies on other components of the platform (like Supabase for authentication) to function correctly.

#### Recommended Method: Full Stack

The best way to run the server for development is as part of the complete suite of services. This ensures all dependencies are available and correctly configured.

From the root of the repository, run:
```bash
make start-dev
```

This command will start the MCP server in a Docker container alongside all other required infrastructure and services.

#### Standalone Method

If you need to run just the MCP server locally, you can do so. First, ensure you have set up the necessary environment variables (e.g., `SUPABASE_URL`, `MCP_TOKEN_SIGNING_SECRET`, etc.) in an `.env` file within the `apps/mcp` directory.

Then, run the following commands from the `apps/mcp` directory:

```bash
# 1. Install dependencies
poetry install

# 2. Run the server (defaults to port 8000)
poetry run python -m mcp_server.main run --port 8002
```

