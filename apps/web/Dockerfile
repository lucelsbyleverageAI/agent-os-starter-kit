# ==================================================
# Web Frontend - Production Build (Next.js)
# ==================================================
# This Dockerfile builds the web frontend from the web app directory context

# Dependencies stage
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy package configuration from current directory (build context)
COPY package*.json yarn.lock* ./

# Install dependencies
RUN yarn --frozen-lockfile --production=false

# Builder stage
FROM node:20-alpine AS builder
WORKDIR /app

# Copy package configuration and node_modules
COPY package*.json yarn.lock* ./
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY . .

# Build arguments for Next.js public environment variables
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_LANGCONNECT_API_URL
ARG NEXT_PUBLIC_MCP_SERVER_URL
ARG NEXT_PUBLIC_LANGGRAPH_API_URL
ARG NEXT_PUBLIC_N8N_URL
ARG NEXT_PUBLIC_WINDMILL_URL
ARG NEXT_PUBLIC_LANGGRAPH_DEPLOYMENT_ID
ARG NEXT_PUBLIC_LANGGRAPH_TENANT_ID
ARG NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID
ARG NEXT_PUBLIC_BASE_API_URL
ARG NEXT_PUBLIC_USE_LANGSMITH_AUTH
ARG NEXT_PUBLIC_GOOGLE_AUTH_DISABLED
ARG NEXT_PUBLIC_BASE_URL
ARG NEXT_PUBLIC_IMAGE_STORAGE_ENABLED
# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ENV MCP_TOKEN_SIGNING_SECRET=$MCP_TOKEN_SIGNING_SECRET
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_LANGCONNECT_API_URL=$NEXT_PUBLIC_LANGCONNECT_API_URL
ENV NEXT_PUBLIC_MCP_SERVER_URL=$NEXT_PUBLIC_MCP_SERVER_URL
ENV NEXT_PUBLIC_LANGGRAPH_API_URL=$NEXT_PUBLIC_LANGGRAPH_API_URL
ENV NEXT_PUBLIC_N8N_URL=$NEXT_PUBLIC_N8N_URL
ENV NEXT_PUBLIC_WINDMILL_URL=$NEXT_PUBLIC_WINDMILL_URL
ENV NEXT_PUBLIC_LANGGRAPH_DEPLOYMENT_ID=$NEXT_PUBLIC_LANGGRAPH_DEPLOYMENT_ID
ENV NEXT_PUBLIC_LANGGRAPH_TENANT_ID=$NEXT_PUBLIC_LANGGRAPH_TENANT_ID
ENV NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID=$NEXT_PUBLIC_LANGGRAPH_DEFAULT_GRAPH_ID
ENV NEXT_PUBLIC_BASE_API_URL=$NEXT_PUBLIC_BASE_API_URL
ENV NEXT_PUBLIC_USE_LANGSMITH_AUTH=$NEXT_PUBLIC_USE_LANGSMITH_AUTH
ENV NEXT_PUBLIC_GOOGLE_AUTH_DISABLED=$NEXT_PUBLIC_GOOGLE_AUTH_DISABLED
ENV NEXT_PUBLIC_BASE_URL=$NEXT_PUBLIC_BASE_URL
ENV NEXT_PUBLIC_IMAGE_STORAGE_ENABLED=$NEXT_PUBLIC_IMAGE_STORAGE_ENABLED
# Build the application
RUN yarn next build

# Production runner stage
FROM node:20-alpine AS runner
WORKDIR /app

# Set production environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy standalone build output - handling the nested app directory structure
# The standalone build creates an 'app' subdirectory due to outputFileTracingRoot
# This includes server.js, node_modules, and .next directories
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone/app/. ./
# Explicitly copy public directory to ensure all assets are available
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
# Static files need to be copied separately as they're not included in standalone
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

# Set hostname and port
ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:3000/api/health || exit 1

# Start the application
CMD ["node", "server.js"] 