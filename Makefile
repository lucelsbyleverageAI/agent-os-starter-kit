# Agent Platform - Development Environment Makefile
#
# Available commands:
#   make start-dev     - Start complete development stack with hot reloading
#   make stop          - Stop all services
#   make clean         - Stop all services and remove volumes (WARNING: Deletes all data!)
#   make export-n8n    - Export n8n workflows and credentials to repo folders

.PHONY: start-dev stop clean export-n8n poetry-install help

# Default target
help:
	@echo "Agent Platform Development Commands:"
	@echo ""
	@echo "Development Stack:"
	@echo "  make start-dev     - Start complete development stack with hot reloading"
	@echo "                      (Docker services + LangGraph/Web locally)"
	@echo ""
	@echo "  make stop          - Stop all services (Docker + background processes)"
	@echo ""
	@echo "  make clean-reset   - Force stop all services and remove ALL data"
	@echo "                      ⚠️  WARNING: This is the most thorough cleanup and will reset everything!"
	@echo ""
	@echo "  make export-n8n    - Export n8n workflows and credentials to repo folders"
	@echo "                      📁 Saves current n8n data for version control"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - .env.local file in project root"
	@echo "  - Docker, Poetry, Yarn installed"
	@echo ""
	@echo "For detailed usage, see scripts/README.md"

# Install Poetry dependencies in all project directories
poetry-install:
	@echo "📦 Installing Poetry dependencies..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Error: Poetry is not installed. Please install Poetry first: https://python-poetry.org/docs/#installation"; exit 1; }
	@echo "  → Installing langgraph dependencies..."
	@cd langgraph && poetry install
	@echo "  → Installing langconnect dependencies..."
	@cd apps/langconnect && poetry install
	@echo "  → Installing MCP server dependencies..."
	@cd apps/mcp && poetry install
	@echo "✅ All Poetry dependencies installed"

# Start complete development stack
start-dev: poetry-install
	@echo "🚀 Starting Agent Platform development stack..."
	@poetry install
	@poetry run python scripts/start_local_services.py

# Stop all services
stop: poetry-install
	@echo "🛑 Stopping all services..."
	@poetry run python scripts/stop_local_services.py

# Force stop all services and remove ALL data (for stuck containers/volumes)
clean-reset: poetry-install
	@echo "🔥 Complete Reset: Forcibly stopping services and removing ALL data..."
	@echo "⚠️  WARNING: This is the most thorough cleanup and will reset everything!"
	@poetry run python scripts/stop_local_services.py --complete-reset --yes

# Export n8n workflows and credentials to repo folders
export-n8n:
	@echo "📁 Exporting n8n workflows and credentials..."
	@./scripts/export-n8n.sh