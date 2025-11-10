#!/bin/bash
# Test Production Database Connection
# This script helps you configure and test your production Supabase connection

set -e

echo "=========================================="
echo "Production Database Connection Test"
echo "=========================================="
echo ""

# Instructions
cat << 'EOF'
Before running this test, you need to get your production Supabase credentials:

1. Go to your Supabase project dashboard
2. Navigate to: Project Settings → Database
3. Under "Connection string" section, select "Connection pooling"
4. You'll see a connection string like:
   postgres://postgres.[PROJECT-REF]:[PASSWORD]@[POOLER-HOST]:6543/postgres

From this, extract:
   - POOLER_HOST: The hostname (e.g., aws-0-us-west-1.pooler.supabase.com)
   - POOLER_PORT: The port (usually 6543 for transaction mode)
   - TENANT_ID: The PROJECT-REF part (e.g., if username is postgres.abc123, then TENANT_ID=abc123)
   - PASSWORD: Your database password

Add these to your .env.local file:
   PROD_POOLER_HOST=your-pooler-hostname.pooler.supabase.com
   PROD_POOLER_PORT=6543
   PROD_DB_PASSWORD=your-password
   PROD_TENANT_ID=your-project-ref
   PROD_DB_NAME=postgres
   PROD_DB_USER=postgres

EOF

echo ""
echo "Checking for required environment variables..."
echo ""

# Check if variables are set
MISSING=0

if [ -z "$PROD_POOLER_HOST" ]; then
    echo "❌ PROD_POOLER_HOST is not set"
    MISSING=1
else
    echo "✅ PROD_POOLER_HOST: $PROD_POOLER_HOST"
fi

if [ -z "$PROD_POOLER_PORT" ]; then
    echo "❌ PROD_POOLER_PORT is not set"
    MISSING=1
else
    echo "✅ PROD_POOLER_PORT: $PROD_POOLER_PORT"
fi

if [ -z "$PROD_DB_PASSWORD" ]; then
    echo "❌ PROD_DB_PASSWORD is not set"
    MISSING=1
else
    echo "✅ PROD_DB_PASSWORD: ****"
fi

if [ -z "$PROD_TENANT_ID" ]; then
    echo "❌ PROD_TENANT_ID is not set"
    MISSING=1
else
    echo "✅ PROD_TENANT_ID: $PROD_TENANT_ID"
fi

if [ -z "$PROD_DB_NAME" ]; then
    echo "⚠️  PROD_DB_NAME not set, using default: postgres"
    export PROD_DB_NAME=postgres
else
    echo "✅ PROD_DB_NAME: $PROD_DB_NAME"
fi

if [ -z "$PROD_DB_USER" ]; then
    echo "⚠️  PROD_DB_USER not set, using default: postgres"
    export PROD_DB_USER=postgres
else
    echo "✅ PROD_DB_USER: $PROD_DB_USER"
fi

echo ""

if [ $MISSING -eq 1 ]; then
    echo "❌ Missing required environment variables."
    echo "Please add them to your .env.local file and try again."
    exit 1
fi

echo "=========================================="
echo "Testing connection to production database..."
echo "=========================================="
echo ""

# Export variables for the pipeline
export POSTGRES_HOST=$PROD_POOLER_HOST
export POSTGRES_PORT=$PROD_POOLER_PORT
export POSTGRES_DB=${PROD_DB_NAME:-postgres}
export POSTGRES_USER=${PROD_DB_USER:-postgres}
export POSTGRES_PASSWORD=$PROD_DB_PASSWORD
export POOLER_TENANT_ID=$PROD_TENANT_ID

echo "Connection details:"
echo "  Host: $POSTGRES_HOST"
echo "  Port: $POSTGRES_PORT"
echo "  Database: $POSTGRES_DB"
echo "  User: $POSTGRES_USER@$POOLER_TENANT_ID"
echo ""

# Run the test-db command
poetry run outcomes-data test-db

echo ""
echo "=========================================="
echo "✅ Connection test completed!"
echo "=========================================="
