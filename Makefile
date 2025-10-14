# Agent Platform - Development Environment Makefile
#
# Available commands:
#   make start-dev     - Start complete development stack with hot reloading
#   make stop          - Stop all services
#   make clean         - Stop all services and remove volumes (WARNING: Deletes all data!)
#   make export-n8n    - Export n8n workflows and credentials to repo folders

.PHONY: start-dev stop clean export-n8n help

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

# Start complete development stack
start-dev:
	@echo "🚀 Starting Agent Platform development stack..."
	@poetry install
	@poetry run python scripts/start_local_services.py

# Stop all services
stop:
	@echo "🛑 Stopping all services..."
	@poetry install
	@poetry run python scripts/stop_local_services.py

# Force stop all services and remove ALL data (for stuck containers/volumes)
clean-reset:
	@echo "🔥 Complete Reset: Forcibly stopping services and removing ALL data..."
	@echo "⚠️  WARNING: This is the most thorough cleanup and will reset everything!"
	@poetry install
	@poetry run python scripts/stop_local_services.py --complete-reset --yes

# Export n8n workflows and credentials to repo folders
export-n8n:
	@echo "📁 Exporting n8n workflows and credentials..."
	@poetry install
	@./scripts/export-n8n.sh
