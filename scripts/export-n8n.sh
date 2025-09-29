#!/bin/bash

# Export n8n workflows and credentials to repo folders
# Usage: ./scripts/export-n8n.sh [workflows|credentials|all]

set -e

CONTAINER_NAME="n8n-dev"
EXPORT_TYPE="${1:-all}"

# Check if n8n container is running
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo "Error: $CONTAINER_NAME container is not running"
    echo "Start it with: make start-dev"
    exit 1
fi

export_workflows() {
    echo "Exporting workflows..."
    docker exec $CONTAINER_NAME n8n export:workflow --all --separate --output=/data/workflows
    # Sanitise exported workflows (remove personal/project metadata)
    node ./scripts/sanitise-n8n.js || true
    echo "✅ Workflows exported to n8n/data/workflows/"
}

export_credentials() {
    echo "Exporting credentials..."
    docker exec $CONTAINER_NAME n8n export:credentials --all --separate --output=/data/credentials
    # Sanitise exported credentials (remove personal/project metadata)
    node ./scripts/sanitise-n8n.js || true
    echo "✅ Credentials exported to n8n/data/credentials/"
}

case $EXPORT_TYPE in
    "workflows")
        export_workflows
        ;;
    "credentials") 
        export_credentials
        ;;
    "all")
        export_workflows
        export_credentials
        ;;
    *)
        echo "Usage: $0 [workflows|credentials|all]"
        echo "  workflows   - Export only workflows"
        echo "  credentials - Export only credentials" 
        echo "  all         - Export both (default)"
        exit 1
        ;;
esac

echo ""
echo "🎉 Export complete! Files are now in your repo and will be imported on next startup."
