# Agent OS Local Deployment Checklist

## Prerequisites

- [ ] **Docker** and **Docker Compose** installed
- [ ] **Python 3.10+** installed
- [ ] **Node.js** and **Yarn** installed

## Initial Setup

### 1. Repository Setup
- [ ] Clone the repository:
  ```bash
  git clone https://github.com/lucelsbyleverageAI/agent-os-starter-kit.git
  cd agent-os-starter-kit
  ```

### 2. Environment Configuration
- [ ] Copy environment template:
  ```bash
  cp .env.local.example .env.local
  ```

## Required Configuration

### 3. Supabase Setup
- [ ] Visit [Supabase Self-Hosting Guide](https://supabase.com/docs/guides/self-hosting/docker)
- [ ] Generate JWT secret, anon key, and service key
- [ ] Update `.env.local` with Supabase credentials:
  ```bash
  SUPABASE_JWT_SECRET=your-jwt-secret
  SUPABASE_ANON_KEY=your-anon-key
  SUPABASE_SERVICE_ROLE_KEY=your-service-key
  ```

### 4. SMTP Configuration
- [ ] Set up email service (Gmail recommended):
  - Go to Google Security → 2-Step Verification → App Passwords
  - Create app password
- [ ] Configure SMTP settings:
  ```bash
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your-email@gmail.com
  SMTP_PASS=your-app-password
  SMTP_ADMIN_EMAIL=admin@your-domain.com
  SMTP_SENDER_NAME="Agent Platform"
  ```

### 5. Generate Security Keys
- [ ] Generate random keys for services:
  ```bash
  # Supabase keys
  SECRET_KEY_BASE=$(openssl rand -base64 64 | tr -d '\n')
  VAULT_ENC_KEY=$(openssl rand -base64 48 | tr -d '\n')
  
  # Dashboard credentials
  DASHBOARD_USERNAME=admin
  DASHBOARD_PASSWORD=your-secure-password
  
  # Service keys
  LANGCONNECT_SERVICE_ACCOUNT_KEY=your-super-secret-internal-admin-key
  MCP_TOKEN_SIGNING_SECRET=your-super-secret-mcp-token-signing-secret
  MCP_SERVICE_ACCOUNT_KEY=your-super-secret-mcp-service-account-key
  
  # n8n keys
  N8N_ENCRYPTION_KEY=your-super-secret-n8n-encryption-key
  N8N_USER_MANAGEMENT_JWT_SECRET=your-super-secret-n8n-jwt-secret
  
  # Windmill database
  SERVICE_USER_POSTGRES=windmill
  SERVICE_PASSWORD_POSTGRES=your-super-secret-windmill-db-password
  ```

### 6. LangSmith Configuration (Required)
- [ ] Get LangSmith API key from [LangSmith](https://smith.langchain.com)
- [ ] Configure tracing:
  ```bash
  LANGSMITH_TRACING=true
  LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com  # or US endpoint
  LANGSMITH_PROJECT=agent-os-dev
  LANGSMITH_API_KEY=ls__your-api-key
  ```

## Optional Configuration

### 7. GCP Image Storage (Optional)
- Using an external image store (e.g. GCP Cloud Storage) helps avoid sending large base64-encoded images between services. If your agents generate images, or you plan to upload images to an agents' image store (in GCP or elsewhere), offloading binary assets to object storage prevents oversized payloads — particularly with LangGraph where thread data can otherwise bloat and slow everything down.
- [ ] If handling image data, configure GCP:
  ```bash
  IMAGE_STORAGE_ENABLED=true
  GCP_PROJECT_ID=your-gcp-project-id
  GCP_STORAGE_BUCKET=your-bucket-name
  GCP_SERVICE_ACCOUNT_KEY=your-base64-encoded-key
  IMAGE_PUBLIC_ACCESS=true
  ```

### 8. Arcade Tool Authentication (Optional)
- [Arcade](https://docs.arcade.dev) is an AI tool-calling platform that enables AI to act securely on behalf of users with authenticated integrations. It provides pre-built connectors for common tools (e.g. Gmail, Microsoft, Asana, GitHub) and handles authentication for you, which makes enabling these tools by default much easier. It works locally for free with an `ARCADE_API_KEY`. For production you will need extra configuration, and there may be costs once you exceed free usage levels. See the Arcade docs for details.
- [ ] Create API key at [Arcade](https://docs.arcade.dev)
- [ ] Configure services:
  ```bash
  ENABLE_ARCADE=true
  ENABLED_ARCADE_SERVICES=microsoft,gmail,google,slack
  ARCADE_API_KEY=your-arcade-api-key
  ```

### 9. Third-Party APIs (Optional)
- You can configure whichever model or provider keys you have; common, useful options include:
  - OpenAI (LLMs)
  - Anthropic (LLMs)
  - Tavily (pre-built search tool in this repo)
  - E2B (code sandbox)
  - Supadata (backend YouTube transcript extraction)

> Note: These are optional, but some features and tools will not work without the relevant API keys.
- [ ] Configure based on needed capabilities:
  ```bash
  # AI Models
  OPENAI_API_KEY=sk-your-openai-key
  ANTHROPIC_API_KEY=your-anthropic-key
  
  # Tools
  TAVILY_API_KEY=your-tavily-key  # For search
  E2B_API_KEY=your-e2b-key        # For code sandbox
  SUPADATA_API_TOKEN=your-token   # For YouTube content extraction
  ```

### 10. Sentry Monitoring (Optional)
- [ ] Configure error tracking:
  ```bash
  SENTRY_DSN_LANGCONNECT=your-dsn
  SENTRY_DSN_MCP=your-dsn
  SENTRY_DSN_WEB=your-dsn
  SENTRY_DSN_LANGGRAPH=your-dsn
  SENTRY_ENVIRONMENT=development
  ```

## Deployment

### 11. Start Services
- [ ] Save `.env.local` file
- [ ] Start the platform:
  ```bash
  make start-dev
  ```
- [ ] Verify all services are running (check console output)

## Initial Platform Setup

### 12. Database Validation
- [ ] Visit Supabase Dashboard: `http://localhost:8000`
- [ ] Log in with dashboard credentials from `.env.local`
- [ ] Check Table Editor for `langconnect` schema
- [ ] Verify migration tables are present

### 13. Create Admin User
- [ ] In Supabase Dashboard → Authentication
- [ ] Create your user account (invite via email or create directly)
- [ ] Sign up/in to the web app: `http://localhost:3000`
- [ ] Verify user appears in `langconnect.user_roles` with `dev_admin` role

### 14. Initialize Agents
- [ ] Go to Agents page in web app
- [ ] Click "Initialize Platform"
- [ ] Verify default agents appear:
  - Tools Agent (basic React agent)
  - Deep Research Agent
  - Deep Agent (file system tasks)
  - Supervisor Agent
  - N8N Agent (streaming responses)

## Service Configuration & Testing

### 15. n8n Setup
- [ ] Visit n8n: `http://localhost:5678`
- [ ] Create n8n account
- [ ] Duplicate pre-loaded agent template
- [ ] Configure OpenAI credentials in template
- [ ] Copy webhook URL from workflow
- [ ] Create N8N Agent in frontend with webhook URL
- [ ] Test streaming responses

### 16. Windmill Setup
- [ ] Visit Windmill: `http://localhost:9000`
- [ ] Create Windmill account
- [ ] Explore workflow capabilities

### 17. MCP Server Testing
- [ ] Check MCP health: `http://localhost:8002/mcp`
- [ ] In separate terminal, run MCP inspector:
  ```bash
  npx @modelcontextprotocol/inspector
  ```
- [ ] Configure inspector:
  - URL: `localhost:8002/mcp`
  - Transport: Streamable HTTP
  - Remove pre-existing auth headers
- [ ] Complete OAuth flow when prompted
- [ ] Test available tools in inspector

### 18. Agent Configuration
- [ ] Configure each agent with available tools from MCP server
- [ ] Test agent functionality with different tool combinations
- [ ] Verify knowledge base integration works
- [ ] Test memory persistence across conversations

## Verification Checklist

### Core Services Running
- [ ] Web Frontend: `http://localhost:3000`
- [ ] Supabase Studio: `http://localhost:8000`
- [ ] LangConnect API: `http://localhost:8080/docs`
- [ ] MCP Server: `http://localhost:8002/mcp`
- [ ] n8n: `http://localhost:5678`
- [ ] Windmill: `http://localhost:9000`
- [ ] LangGraph Studio: Opens automatically on `http://localhost:2024`