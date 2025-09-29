# ==================================================
# LangConnect RAG API - Production Build
# ==================================================

# Build stage
FROM python:3.11-slim as builder

# Set environment variables for build
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/opt/poetry-cache

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
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
COPY . .

# Install the package
RUN poetry install --only-root

# Production stage
FROM python:3.11-slim as runtime

# Set environment variables for production
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    HOME="/home/langconnect"

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security with home directory
RUN groupadd -r langconnect && useradd -r -g langconnect -m -d /home/langconnect langconnect

# Set work directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy source code from builder stage
COPY --from=builder /app/langconnect /app/langconnect

# Create data directory and set permissions
RUN mkdir -p /app/data /app/logs && \
    chown -R langconnect:langconnect /app /home/langconnect

# Switch to non-root user
USER langconnect

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Production command (no hot reload)
CMD ["uvicorn", "langconnect.server:APP", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--log-level", "info"] 