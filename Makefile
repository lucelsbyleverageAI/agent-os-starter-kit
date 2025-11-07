# Agent Platform - Development Environment Makefile
#
# Available commands:
#   make start-dev     - Start complete development stack with hot reloading
#   make stop          - Stop all services
#   make clean         - Stop all services and remove volumes (WARNING: Deletes all data!)
#   make export-n8n    - Export n8n workflows and credentials to repo folders
#   make export-collection NAME="Collection Name" - Export a collection from local
#   make import-collection FILE=export.json ENV=production - Import a collection

.PHONY: start-dev start-demo stop clean-reset export-n8n export-collection import-collection help

# Default target
help:
	@echo "Agent Platform Development Commands:"
	@echo ""
	@echo "Development Stack:"
	@echo "  make start-dev     - Start complete development stack with hot reloading"
	@echo "                      (Docker services + LangGraph/Web locally)"
	@echo ""
	@echo "  make start-demo    - Start in production/demo mode (builds instead of dev)"
	@echo "                      🏭 Runs production builds for LangGraph and Web"
	@echo ""
	@echo "  make stop          - Stop all services (Docker + background processes)"
	@echo ""
	@echo "  make clean-reset   - Force stop all services and remove ALL data"
	@echo "                      ⚠️  WARNING: This is the most thorough cleanup and will reset everything!"
	@echo ""
	@echo "  make export-n8n    - Export n8n workflows and credentials to repo folders"
	@echo "                      📁 Saves current n8n data for version control"
	@echo ""
	@echo "Collection Migration:"
	@echo "  make export-collection NAME=\"Collection Name\" [ENV=local]"
	@echo "                      📤 Export a collection to JSON file"
	@echo ""
	@echo "  make import-collection FILE=export.json ENV=production"
	@echo "                      📥 Import a collection from JSON file"
	@echo "                      Add DRY_RUN=true to validate without importing"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - .env.local file in project root"
	@echo "  - Docker, Poetry, Yarn installed"
	@echo ""
	@echo "For detailed usage, see scripts/README.md and database/collection_transfer/README.md"

# Start complete development stack
start-dev:
	@echo "🚀 Starting Agent Platform development stack..."
	@poetry install
	@poetry run python scripts/start_local_services.py

# Start complete production/demo stack (with builds)
start-demo:
	@echo "🚀 Starting Agent Platform in production/demo mode..."
	@poetry install
	@poetry run python scripts/start_local_services.py --production

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

# Collection migration commands
export-collection:
	@if [ -z "$(NAME)" ]; then \
		echo "❌ Error: NAME parameter required"; \
		echo "Usage: make export-collection NAME=\"Collection Name\" [ENV=local]"; \
		exit 1; \
	fi
	@echo "📤 Exporting collection: $(NAME)"
	@python database/collection_transfer/export_collections.py \
		--collection-name "$(NAME)" \
		--source-env $(or $(ENV),local) \
		--output database/exports/$(shell echo "$(NAME)" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')_$(shell date +%Y%m%d_%H%M%S).json \
		--pretty

import-collection:
	@if [ -z "$(FILE)" ]; then \
		echo "❌ Error: FILE parameter required"; \
		echo "Usage: make import-collection FILE=export.json ENV=production [DRY_RUN=true]"; \
		exit 1; \
	fi
	@if [ -z "$(ENV)" ]; then \
		echo "❌ Error: ENV parameter required"; \
		echo "Usage: make import-collection FILE=export.json ENV=production [DRY_RUN=true]"; \
		exit 1; \
	fi
	@if [ "$(DRY_RUN)" = "true" ]; then \
		echo "🔍 Validating import (dry-run): $(FILE) → $(ENV)"; \
		python database/collection_transfer/import_collections.py \
			--file $(FILE) \
			--target-env $(ENV) \
			--dry-run; \
	else \
		echo "📥 Importing collection: $(FILE) → $(ENV)"; \
		python database/collection_transfer/import_collections.py \
			--file $(FILE) \
			--target-env $(ENV); \
	fi
