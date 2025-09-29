# Agent OS Production Deployment Checklist

## 1. Domain Purchase

- [ ] Purchase a domain from a registrar
  - **Recommended**: [Hostinger](https://hostinger.com) for simplicity and competitive pricing
  - Choose any domain name you prefer
  - Consider `.com` for professional use or country-specific domains for regional projects

## 2. Server Provider Selection

Most major VPS providers will work fine for this deployment. We recommend **Hetzner** for this guide because:
- Cost-effective pricing
- Reliable performance and network
- Straightforward interface
- European data centers (good for GDPR compliance)

**Alternative providers**: DigitalOcean, Linode, Vultr, or any VPS provider supporting Ubuntu and Docker.

## 3. Server Configuration

### Recommended Server Specifications

**Hetzner CPX41**: 8 shared vCPU, 16GB RAM, 240GB SSD (~$30/month)

**Why these specs?**
- **Coolify Requirements**: 2 vCPU + 2GB RAM minimum
- **Agent OS Components**: ~4-5 vCPU + 6GB RAM for all services
- **Headroom**: Extra capacity for traffic spikes and background processes
- **Shared vCPU**: Sufficient since heavy AI processing runs on LangGraph Cloud

**Alternative**: CPX31 (4 vCPU, 8GB RAM) if budget-conscious, but less headroom.

### Server Setup Settings

When creating your Hetzner server:

**Required Settings:**
- [ ] **Image**: Ubuntu 22.04 LTS (most tested with Coolify)
- [ ] **Type**: CPX41 (shared vCPU)
- [ ] **Location**: Choose closest to your users
- [ ] **SSH Key**: Add your public SSH key (see below for creation steps)
- [ ] **IPv4 & IPv6**: Enable both

#### SSH Key Creation

- Generate an ED25519 keypair dedicated to server access, then add the public key to your provider's SSH key settings.

macOS/Linux:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_server -C "server-access@yourdomain.com"
```

- When prompted, enter a strong passphrase. Then display your public key:

```bash
cat ~/.ssh/id_ed25519_server.pub
```

Windows (PowerShell):

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519_server -C "server-access@yourdomain.com"
```

- When prompted, enter a strong passphrase. Then display (or copy) your public key:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519_server.pub
```

- Optional (copy to clipboard):

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519_server.pub | Set-Clipboard
```

- Copy the entire public key (the `.pub` file content) and add it to the Hetzner SSH Key configuration.


**Firewall Configuration:**
- [ ] **Port 22**: SSH access
- [ ] **Port 80**: HTTP (for redirects and Let's Encrypt)
- [ ] **Port 443**: HTTPS (main application traffic)
- [ ] **Port 8000**: Coolify dashboard (temporary, will be moved behind domain)

**Skip These Settings** (not needed for initial setup):
- [ ] Volumes
- [ ] Backups (configure later)
- [ ] Placement groups
- [ ] Labels
- [ ] Cloud config

## 4. Architecture Decision: Single vs Multi-Server

### Recommended: Separate Servers
**Ideal production setup**:
- **Server 1**: Coolify management instance
- **Server 2**: Agent OS applications

**Benefits**:
- If applications consume high resources, Coolify dashboard remains accessible
- Better security isolation
- Easier to scale individual components
- More resilient to failures

### Demo Setup: Single Server
**For this guide, we'll use one server** because:
- Simpler to demonstrate
- Lower cost for getting started
- Agent OS workload is lighter with LangGraph on cloud
- Can always migrate to multi-server later

## 5. Installation Process

### Step 1: Connect to Server 
```bash
ssh root@your-server-ip
```

Or to force a specific ssh key:

```bash
ssh -i ~/.ssh/id_ed25519_server root@your-server-ip
```

### Step 2: Update System Packages

**Before installing anything, update the system:**

```bash
apt update && apt upgrade -y
```

This ensures all system packages are current and security patches are applied.

If kernel updates were installed, reboot the server:

```bash
reboot
```

Wait 2-3 minutes, then reconnect via SSH.

### Step 3: Install Coolify with Predefined Admin User

Instead of using the basic installation script, we'll create a secure admin user during installation to avoid exposing a public registration page.

**Prepare your credentials** (must meet requirements):
- **Username**: 3-255 characters, letters/numbers/spaces/underscores/hyphens only
- **Email**: Valid email address with proper DNS
- **Password**: 8+ chars, uppercase, lowercase, number, special character

**Installation command**:
```bash
sudo -E env ROOT_USERNAME="admin" ROOT_USER_EMAIL="your-email@yourdomain.com" ROOT_USER_PASSWORD="YourSecurePassword123!" bash -c 'curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash'
```

**Why use environment variables?**
- Prevents public registration page exposure
- No window for unauthorized admin access
- Fully automated secure setup
- Production best practice

### What the Installation Script Does

The Coolify installer automatically handles:
- Docker installation and configuration
- Required system packages
- SSH key generation for server management
- Directory structure creation
- Security configurations
- Service startup

## 6. Domain and SSL Configuration

### Step 1: Configure DNS Records

In your domain registrar (e.g., Hostinger), set up these DNS records:

**Replace any existing A records, don't add additional ones:**

- **Type**: A, **Name**: @ (or blank), **Points to**: your-server-ip, **TTL**: 300 (or lowest value)
- **Type**: A, **Name**: *, **Points to**: your-server-ip, **TTL**: 300 (or lowest value)

**Optional IPv6 records:**
- **Type**: AAAA, **Name**: @ (or blank), **Points to**: your-server-ipv6, **TTL**: 300 (or lowest value)
- **Type**: AAAA, **Name**: *, **Points to**: your-server-ipv6, **TTL**: 300 (or lowest value)

### Step 2: Access Coolify

Access the Coolify dashboard while port 8000 is open:

1. Open `http://your-server-ip:8000` in your browser
2. Log in with the credentials you created during installation
3. Click "Get Started" and select "localhost" as the server
### Step 3: Switch to Caddy Proxy

**IMPORTANT: Do this before configuring domains in coolify**

While port 8000 is still open and accessible:

- Go to **Servers** → **localhost** → **Proxy** tab
- Click "**Stop Proxy**" (if Traefik is running)
- Click "**Switch Proxy**"
- Select "**Caddy**" (now fully supported, no longer beta)
- Click "**Start Proxy**"

Wait for Caddy to start successfully.

### Step 4: Configure Server Wildcard Domain

Still in **Servers** → **localhost**
1. Set **Wildcard Domain** to: `https://yourdomain.com`
2. **Save**

### Step 5: Configure Instance Domain

Go to **Settings** (in sidebar)
1. Set **Domain** to: `https://coolify.yourdomain.com`
2. **Uncheck "Validate DNS settings"** (can be unreliable)
3. **Save**

### Step 6: Test DNS and HTTPS Access

- **Wait 2-5 minutes** for DNS propagation
- **Test DNS resolution**:

```bash
nslookup coolify.yourdomain.com
```

Should return your server IP

- **Test HTTPS access**: Visit `https://coolify.yourdomain.com`
- **Login** with your credentials to verify SSL is working (look for green lock icon)

## 7. Security Hardening

### Close Port 8000

**Only after confirming HTTPS access works:**

1. **Go to Hetzner firewall settings**
2. **Remove the rule for port 8000**
3. **Test security**:
   - Confirm `http://your-server-ip:8000` no longer works
   - Verify `https://coolify.yourdomain.com` still works

### Enable Additional Security (Recommended)

In Coolify dashboard:
- [ ] **Enable 2FA** in Profile settings
- [ ] **Review user permissions** in Teams
- [ ] **Set up backup monitoring** for critical data

## 8. Deploy Agent OS Application Stack

### Step 1: Prepare Repository (clone, edit Caddy labels, push)

1. **Clone the repository (if you haven't already):**

   ```bash
   git clone https://github.com/lucelsbyleverageAI/agent-os-starter-kit.git
   cd agent-os-starter-kit
   ```

2. **Edit Docker Compose Caddy labels with your domains:**

   The Caddy labels in your production Docker Compose must contain hardcoded hostnames (environment variables don't work inside labels). Update the services you plan to expose with your purchased domain, for example: frontend app, Supabase, MCP, n8n, Windmill, langconnect.

   ```yaml
   labels:
         - caddy=servicename.yourdomain.com
         - caddy.reverse_proxy={{upstreams 8000}}
   ```

   Replace placeholders with actual hostnames like:
   - `app.yourdomain.com` (frontend)
   - `supabase.yourdomain.com` (Supabase)
   - `mcp.yourdomain.com` (MCP)
   - `n8n.yourdomain.com` (n8n)
   - `windmill.yourdomain.com` (Windmill)
   - `langconnect.yourdomain.com` (LangConnect API)

3. **Commit and push your changes** to your remote repository (GitHub or your chosen remote):

   ```bash
   git add .
   git commit -m "Configure Caddy labels for production domains"
   git push
   ```

### Step 2: Set Up GitHub App Integration

1. **In Coolify**: Go to **Sources** → **Create GitHub App**
2. **Webhook URL**: Use `https://coolify.yourdomain.com`
3. **Follow the GitHub authorization flow** to install the app
4. **Grant access** to your Agent OS repository

### Step 3: Create New Project in Coolify

1. **Projects** → **Add New Project**
2. **Name**: Agent OS Production (or other name)
3. **Environment**: Production
4. **Add Resource** → **Private Repository (GitHub App)**
5. **Select**: The repository you just pushed
6. **Build Pack**: Docker Compose
7. **Docker Compose Location**: `docker-compose.production.yml`
8. **Click**: Load Repository

### Step 4: Configure Environment Variables

Copy all required environment variables from the `.env.production.coolify.example` file into **Developer View** and update values as needed.

### Step 5: Deploy Application Stack

1. **Click Deploy** in Coolify
2. **Wait 10-20 minutes** for initial build and deployment
3. **Monitor logs** for any errors
4. **Verify all containers** are running

### Step 6: Initial Application Setup

**Create First User:**
1. Visit Supabase Studio: `https://supabase.yourdomain.com` and log in with your supabase username and password
2. Go to **Authentication** → **Users**
3. Create your admin user (first user gets `dev_admin` role automatically) - via email or directly in the dashboard

**Test Services:**
- [ ] **Frontend**: `https://app.yourdomain.com` - Should load login page
- [ ] **Supabase**: `https://supabase.yourdomain.com` - API should respond
- [ ] **MCP Server**: `https://mcp.yourdomain.com/mcp` - Health check should work
- [ ] **n8n**: `https://n8n.yourdomain.com` - Sign up for your instance (Chrome may initially warn about the new subdomain; certificates should be valid—proceed to the site if prompted)
- [ ] **Windmill**: `https://windmill.yourdomain.com` - Sign up for your instance

### Step 7: Test Remote 3rd Party MCP Connection

Once you have a user set up and the MCP server live, you should be able to connect to the MCP from any 3rd party client that has remote MCP server support - e.g., by running npx @modelcontextprotocol/inspector, Claude.ai or ChatGPT (via the 'Connections' settings). 

Use the url: `https://mcp.yourdomain.com/mcp`

When you set this up, it will ask you to authenticate as the user and then you should see the tools configure in the 3rd party client.

## 9. Deploy LangGraph to LangGraph Cloud

### Step 1: Create LangGraph Deployment

1. **Go to**: [LangGraph Cloud Platform](https://smith.langchain.com)
2. **New Deployment** → **Connect to GitHub**
3. **Select**: Your Agent OS repository (set langgraph.json location to `langgraph/langgraph.json`)
4. **Choose Environment**: Development/Production (one free development per account, requires seat)
5. **Configure Build Settings**: Defaults should work

### Step 2: Configure LangGraph Environment Variables

Copy this template into the LangGraph environment configuration:

```bash
# API Keys for Tools
ARCADE_API_KEY=your-arcade-key
TAVILY_API_KEY=your-tavily-key
E2B_API_KEY=your-e2b-key
ANTHROPIC_API_KEY=your-anthropic-key
OPENAI_API_KEY=your-openai-key

# Agent OS Integration URLs
LANGGRAPH_MCP_SERVER_URL=https://mcp.yourdomain.com
SUPABASE_PUBLIC_URL=https://supabase.yourdomain.com
SUPABASE_ANON_KEY=your-supabase-anon-key
FRONTEND_BASE_URL=https://app.yourdomain.com

# Service Account Authentication
LANGCONNECT_SERVICE_ACCOUNT_KEY=your-service-account-key
MCP_SERVICE_ACCOUNT_KEY=your-service-account-key
MCP_TOKEN_SIGNING_SECRET=your-mcp-token-secret

# Arcade Configuration (Optional)
ENABLE_ARCADE=false
ENABLED_ARCADE_SERVICES=microsoft,gmail,google,slack

# Image Storage (Optional)
IMAGE_STORAGE_ENABLED=false
GCP_PROJECT_ID=your-gcp-project-id
GCP_STORAGE_BUCKET=your-bucket-name
GCP_SERVICE_ACCOUNT_KEY=your-base64-key
IMAGE_PUBLIC_ACCESS=true

# Monitoring
SENTRY_DSN_LANGGRAPH=
SENTRY_ENVIRONMENT=development
SENTRY_TRACES_SAMPLE_RATE=1.0
SENTRY_PROFILES_SAMPLE_RATE=0.0
```

### Step 3: Deploy and Collect Configuration

1. **Click Deploy** in LangGraph Cloud
2. **Wait for deployment** to complete
3. **Collect these values** from the LangGraph dashboard:
   - **Tenant ID**: Found in URL parameters
   - **Deployment ID**: Found in dashboard or URL
   - **API URL**: Displayed in deployment dashboard (e.g., `https://xxx.langgraph.app`)

### Step 4: Update Coolify with LangGraph Configuration

**Add/Update these environment variables in Coolify:**

```bash
LANGGRAPH_EXTERNAL_URL=https://your-deployment.langgraph.app
NEXT_PUBLIC_LANGGRAPH_API_URL=https://your-deployment.langgraph.app
NEXT_PUBLIC_LANGGRAPH_TENANT_ID=your-tenant-id
NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID=tools_agent
```

**Redeploy the application stack** in Coolify to apply changes.

## 10. Initialize and Test Platform

### Initialize Agents

1. **Login** to `https://app.yourdomain.com` as dev_admin user
2. **Go to Agents page**
3. **Click "Initialize Platform"**
4. **Verify** default agents appear:
   - Tools Agent
   - Deep Research Agent
   - Deep Agent
   - Supervisor Agent
   - N8N Agent

### Test Agent Functionality

- [ ] **Create new chat** and test Tools Agent
- [ ] **Verify tool execution** works (web search, calculator, etc.)
- [ ] **Test knowledge base** upload and retrieval
- [ ] **Check agent memory** persistence across conversations

### Configure n8n Agent (Optional)

1. **In n8n** (`https://n8n.yourdomain.com`):
   - Duplicate the pre-loaded agent template
   - Configure OpenAI credentials
   - Set webhook to streaming mode
   - Copy webhook URL

2. **In Agent OS Frontend**:
   - Create new N8N Agent
   - Paste webhook URL
   - Test streaming responses

## 11. Post-Deployment Verification

- [ ] **All services accessible** via HTTPS with valid certificates
- [ ] **User authentication** works across all services
- [ ] **Agent chat** functional with LangGraph integration
- [ ] **Tool execution** working (MCP server responding)
- [ ] **Knowledge base** operational (document upload/search)
- [ ] **n8n workflows** can be created and executed
- [ ] **Windmill scripts** can be created and run
- [ ] **Third-party MCP clients** can connect successfully

## 12. Production Considerations

### Monitoring Setup
- [ ] Configure Sentry error tracking (if enabled)
- [ ] Set up uptime monitoring (UptimeRobot, Pingdom, etc.)
- [ ] Monitor resource usage in Coolify dashboard
- [ ] Set up log aggregation for troubleshooting

### Backup Strategy
- [ ] Configure automated database backups
- [ ] Back up environment variables securely
- [ ] Document disaster recovery procedures
- [ ] Test backup restoration process

### Security Hardening
- [ ] Enable 2FA for all admin accounts
- [ ] Review and restrict API keys/service accounts
- [ ] Set up rate limiting if needed
- [ ] Regular security updates via Coolify

### Performance Optimization
- [ ] Monitor LangGraph Cloud usage and costs
- [ ] Optimize database queries if needed
- [ ] Configure CDN for static assets (optional)
- [ ] Adjust worker counts for n8n/Windmill based on load

## Next Steps

Your production AI Agent Platform is now live! You can:

1. **Create custom agents** using the LangGraph framework
2. **Build n8n workflows** for automation
3. **Develop Windmill scripts** for data processing
4. **Create knowledge bases/collections** for RAG capabilities
5. **Integrate with third-party tools** via MCP
6. **Scale services** as needed through Coolify

## Cost Summary (Monthly)

- **Hetzner CPX41**: ~$30
- **Domain**: €1-2
- **LangGraph Cloud**: Free tier (Development environment) plus seat at ~$40/month
- **Total Base Cost**: ~$70/month

**Additional costs may include:**
- LangGraph production environment usage
- API usage (OpenAI, Anthropic, etc.)
- Additional server resources if scaling
- Premium monitoring services Post-Installation Verification

