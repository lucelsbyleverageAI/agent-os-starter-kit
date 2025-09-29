# ==================================================
# MCP Server - Production Build
# ==================================================

# Build stage
FROM python:3.11-slim as builder

# Set environment variables for build
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/opt/poetry-cache \
    PYTHONPATH=/app/src

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --upgrade pip setuptools wheel poetry

# Set work directory
WORKDIR /app

# Copy Poetry files
COPY pyproject.toml poetry.lock* README.md ./

# Configure Poetry to use project directory and install dependencies
RUN poetry config virtualenvs.in-project true && \
    poetry install --only=main --no-root && \
    rm -rf /opt/poetry-cache

# Copy source code
COPY src/ ./src/

# Install the package
RUN poetry install --only-root

# Production stage
FROM python:3.11-slim as runtime

# Set environment variables for production
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    HOME="/home/mcpserver"

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security with home directory
RUN groupadd -r mcpserver && useradd -r -g mcpserver -m -d /home/mcpserver mcpserver

# Set work directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy source code from builder stage
COPY --from=builder /app/src /app/src

# Create data directory and set permissions
RUN mkdir -p /app/data /app/logs && \
    chown -R mcpserver:mcpserver /app /home/mcpserver

# Switch to non-root user
USER mcpserver

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Production command (no hot reload)
CMD ["python", "-m", "mcp_server.main", "run", "--transport", "http", "--host", "0.0.0.0", "--port", "8001"] 