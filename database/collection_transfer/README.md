# Collection Transfer Tool

Tool for exporting and importing knowledge base collections between environments (local ↔ staging ↔ production).

## Features

- **Export collections** to portable JSON files with all data:
  - Collection metadata
  - Documents (full content)
  - Embeddings (vector data)
  - Permissions
- **User ID mapping** between environments:
  - Email-based matching
  - Explicit UUID mappings
  - Fallback to default owner
- **Safe imports** with:
  - Dry-run validation
  - Transaction rollback on failure
  - Duplicate detection
- **SSH tunnel support** for secure production access

## Quick Start

### 1. Configure Environments

Edit `database/transfer_configs/environments.yml`:

```yaml
environments:
  local:
    host: localhost
    port: 5432
    database: postgres
    user: postgres.1000  # Include tenant ID for Supavisor pooler

  production:
    host: localhost  # Via SSH tunnel (see step 2)
    port: 5433       # Local port that tunnels to production
    database: postgres
    user: postgres
```

**Important**: Passwords are NOT stored in config files. Add them to `.env.local`:

```bash
# In .env.local
POSTGRES_PASSWORD=localpass                     # For local environment
POSTGRES_PASSWORD_PRODUCTION=your-prod-password # For production
```

### 2. Set Up Production SSH Tunnel (One-Time Setup)

If your production database requires SSH access:

#### A. Find Your Database Container IP

```bash
# SSH to production server
ssh your-production-server

# Find database container
docker ps | grep postgres

# Get container IP (if database is in Docker and not exposed to localhost)
docker inspect db_prod-xxxxx | grep IPAddress
# Example output: "IPAddress": "172.18.0.7"
```

#### B. Configure Tunnel Script

Edit `database/collection_transfer/tunnel_to_production.sh`:

```bash
PRODUCTION_SSH_HOST="your-production-server"  # Your SSH hostname
DB_CONTAINER_IP="172.18.0.7"                  # From step A, or "localhost" if DB is on host
DB_PORT="5432"                                # Production DB port
LOCAL_PORT="5433"                             # Local port (must match environments.yml)
```

#### C. Open Tunnel Before Migrations

```bash
# Open tunnel (keep terminal open during migration)
./database/collection_transfer/tunnel_to_production.sh

# Test connection in another terminal
python3 database/collection_transfer/test_prod_connection.py
```

### 3. Configure User Mappings

Edit `database/transfer_configs/user_mappings.yml`:

```yaml
# IMPORTANT: Replace with your actual admin emails for each environment
default_owners:
  local: "admin@yourcompany.com"
  production: "admin@yourcompany.com"

permission_strategy:
  missing_user_action: "assign_to_default_owner"
  preserve_permission_levels: true
  skip_system_permissions: true
```

### 4. Export Collections

Export all collections:

```bash
make export-collection ENV=local
```

Export specific collection:

```bash
make export-collection NAME="my_collection" ENV=local
```

Or use Python directly:

```bash
# Export all
python -m database.collection_transfer.export_collections \
  --all \
  --source-env local \
  --output database/exports/all_collections.json \
  --pretty

# Export by name
python -m database.collection_transfer.export_collections \
  --collection-name "My Collection" \
  --source-env local

# Export without embeddings (faster, smaller file)
python -m database.collection_transfer.export_collections \
  --collection-name "Test" \
  --no-embeddings
```

### 5. Import Collections

**Always run dry-run first:**

```bash
make import-collection FILE=database/exports/file.json ENV=production DRY_RUN=true
```

If validation succeeds, import for real:

```bash
make import-collection FILE=database/exports/file.json ENV=production
```

Or use Python directly:

```bash
# Dry-run validation
python -m database.collection_transfer.import_collections \
  --file database/exports/file.json \
  --target-env production \
  --dry-run

# Actual import
python -m database.collection_transfer.import_collections \
  --file database/exports/file.json \
  --target-env production
```

## Configuration Details

### Environment Configuration (`environments.yml`)

Defines database connection details. Passwords come from `.env.local` environment variables:

```yaml
environments:
  local:
    host: localhost
    port: 5432
    database: postgres
    user: postgres.1000  # Include tenant ID for Supavisor pooler
    description: "Local development database"

  production:
    host: localhost  # Via SSH tunnel
    port: 5433       # Tunnel local port
    database: postgres
    user: postgres
    description: "Production database via SSH tunnel"

defaults:
  source: local
  target: production
```

**Password Resolution Order:**
1. `POSTGRES_PASSWORD_{ENV_NAME}` (e.g., `POSTGRES_PASSWORD_PRODUCTION`)
2. `POSTGRES_PASSWORD` (fallback)

### User Mapping Configuration (`user_mappings.yml`)

Controls how user IDs are translated between environments.

#### Default Owners (Required)

Set the admin email for each environment in `.env.local` or directly in the config:

```yaml
default_owners:
  local: "admin@yourcompany.com"
  staging: "admin@yourcompany.com"
  production: "admin@yourcompany.com"
```

When a user doesn't exist in the target environment, permissions are assigned to this user.

#### Email-Based Mapping (Automatic)

Users with the same email in both environments are automatically matched. No configuration needed!

Example:
- Local: `user@company.com` (UUID: abc-123)
- Production: `user@company.com` (UUID: xyz-789)
- Result: Permission automatically mapped

#### Explicit UUID Mappings (Optional)

For edge cases where users have different emails across environments:

```yaml
explicit_mappings:
  local_to_production:
    "local-user-uuid": "prod-user-uuid"

  production_to_local:
    "prod-user-uuid": "local-user-uuid"
```

#### Permission Strategy

```yaml
permission_strategy:
  # What to do when user doesn't exist in target
  # Options: "assign_to_default_owner", "skip", "fail"
  missing_user_action: "assign_to_default_owner"

  # Whether to keep original permission level (viewer/editor/owner)
  preserve_permission_levels: true

  # Skip system-granted permissions (they're auto-created by triggers)
  skip_system_permissions: true
```

## Production SSH Tunnel Setup

### Why SSH Tunneling?

Production databases should NOT expose PostgreSQL port 5432 to the internet for security. SSH tunneling provides secure, encrypted access.

### How It Works

```
Your Machine → SSH Tunnel → Production Server → Docker Container
localhost:5433 ---------> your-server:22 -----> 172.18.0.7:5432
```

### Tunnel Script Configuration

The `tunnel_to_production.sh` script needs these variables configured:

```bash
PRODUCTION_SSH_HOST="your-production-server"   # SSH hostname or user@host
DB_CONTAINER_IP="172.18.0.7"                   # Docker container IP or "localhost"
DB_PORT="5432"                                  # Database port
LOCAL_PORT="5433"                               # Must match environments.yml
```

### Finding Database Container IP

If PostgreSQL runs in Docker and doesn't expose port 5432 to localhost:

```bash
# Method 1: Inspect container
ssh your-server
docker ps | grep postgres                    # Find container name
docker inspect CONTAINER_NAME | grep IPAddress

# Method 2: Use docker exec
docker exec CONTAINER_NAME hostname -I
```

### Testing the Tunnel

```bash
# Terminal 1: Open tunnel
./database/collection_transfer/tunnel_to_production.sh

# Terminal 2: Test connection
python3 database/collection_transfer/test_prod_connection.py
```

Expected output:
```
✅ Found N production users:
   user@company.com → ad5eb4f3-...
✅ Connection successful!
```

## Export File Format

Exports are JSON files with this structure:

```json
{
  "export_metadata": {
    "version": "1.0",
    "format": "collection_export",
    "source_environment": "local",
    "exported_at": "2025-11-07T10:26:05Z",
    "collection_count": 10
  },
  "user_directory": {
    "user-uuid": {
      "email": "user@example.com",
      "display_name": "User Name",
      "role": "dev_admin"
    }
  },
  "collections": [
    {
      "collection": { /* metadata */ },
      "documents": [ /* content */ ],
      "embeddings": [ /* vectors */ ],
      "permissions": [ /* access control */ ],
      "stats": {
        "document_count": 7,
        "embedding_count": 660,
        "permission_count": 3
      }
    }
  ]
}
```

## Common Workflows

### Workflow 1: Local → Production Migration (Full Stack)

```bash
# 1. Add production password to .env.local (one-time)
echo "POSTGRES_PASSWORD_PRODUCTION=your-password" >> .env.local

# 2. Configure user mappings (one-time)
vim database/transfer_configs/user_mappings.yml
# Update default_owners with your admin emails

# 3. Configure and start SSH tunnel (one-time setup, then run before migrations)
vim database/collection_transfer/tunnel_to_production.sh  # Update SSH host and DB IP
./database/collection_transfer/tunnel_to_production.sh &

# 4. Test connection
python3 database/collection_transfer/test_prod_connection.py

# 5. Export all collections from local
make export-collection ENV=local

# 6. Dry-run import to production
make import-collection FILE=database/exports/all_collections_*.json ENV=production DRY_RUN=true

# 7. Review output, then import for real
make import-collection FILE=database/exports/all_collections_*.json ENV=production
```

### Workflow 2: Single Collection Migration

```bash
# Export
make export-collection NAME="e18_business_cases" ENV=local

# Validate
make import-collection FILE=database/exports/e18_business_cases_*.json ENV=production DRY_RUN=true

# Import
make import-collection FILE=database/exports/e18_business_cases_*.json ENV=production
```

### Workflow 3: Pull Production Data to Local for Testing

```bash
# 1. Open tunnel to production
./database/collection_transfer/tunnel_to_production.sh &

# 2. Export from production
python -m database.collection_transfer.export_collections \
  --collection-name "Production Collection" \
  --source-env production \
  --output database/exports/prod_data.json

# 3. Import to local
make import-collection FILE=database/exports/prod_data.json ENV=local
```

### Workflow 4: Backup All Collections

```bash
# Backup production
./database/collection_transfer/tunnel_to_production.sh &
python -m database.collection_transfer.export_collections \
  --all \
  --source-env production \
  --output database/exports/backup_$(date +%Y%m%d).json \
  --pretty
```

## User Mapping Resolution Order

When importing, user IDs are resolved in this order:

1. **Skip system permissions** (if configured) - System-granted permissions are skipped
2. **Explicit UUID mapping** - Check `explicit_mappings` in config
3. **Email match** - Find user by email in target environment
4. **Default owner fallback** - Assign to `default_owners[target_env]`
5. **Strategy enforcement** - Apply `missing_user_action` (assign/skip/fail)

## Troubleshooting

### Connection Issues

#### "Tenant or user not found" (Local)

**Problem**: Supavisor pooler requires tenant ID

**Solution**: Use tenant-qualified username in `environments.yml`:
```yaml
local:
  user: postgres.1000  # Include tenant ID
```

#### Connection Timeout (Production)

**Problem**: Can't connect to production database

**Solutions**:
1. Ensure SSH tunnel is open: `./database/collection_transfer/tunnel_to_production.sh`
2. Check SSH host is correct in tunnel script
3. Verify database container IP is correct
4. Test SSH access: `ssh your-production-server`

#### "Password authentication failed"

**Problem**: Wrong password or missing environment variable

**Solutions**:
1. Check `.env.local` has correct password:
   ```bash
   POSTGRES_PASSWORD_PRODUCTION=your-actual-password
   ```
2. Verify password works by testing connection
3. Check password doesn't have special characters that need escaping

### User Mapping Issues

#### "Default owner not found"

**Problem**: Default owner email doesn't exist in target database

**Solution**: Ensure default owner exists:
```bash
# Check production users
python3 database/collection_transfer/test_prod_connection.py

# Update user_mappings.yml with valid email
default_owners:
  production: "actual-user@company.com"  # Must exist in production
```

#### Permissions Not Mapping

**Problem**: Users have different emails across environments

**Solution**: Use explicit UUID mappings:
```yaml
explicit_mappings:
  local_to_production:
    "local-uuid": "prod-uuid"
```

### Import Issues

#### "Collection UUID already exists"

**Problem**: Collection already exists in target

**Solutions**:
1. This is expected for re-imports (idempotent)
2. Import will update existing collection
3. Use different collection name if you want a copy

#### "Import failed: rollback"

**Problem**: Error during import, transaction rolled back

**Solutions**:
1. Check error message for specific issue
2. Run with `--dry-run` first to validate
3. Check database permissions
4. Verify embeddings are valid vectors

## File Size Considerations

Vector embeddings make export files large:

- Small (100 chunks): ~500 KB
- Medium (1,000 chunks): ~5 MB
- Large (10,000 chunks): ~50 MB
- Your 10 collections: ~49 MB with 2,264 embeddings

**Tips:**
- Use `--no-embeddings` for faster testing
- Compress exports: `gzip database/exports/file.json`
- Export collections individually for better control
- The `.gitignore` already excludes `database/exports/`

## Security Notes

### Sensitive Data

1. **Never commit `.env.local`** - Contains production passwords
2. **Never commit export files** - Contains full document content
3. **Secure export transfers** - Use encrypted channels (SCP, encrypted storage)
4. **User directory** - Export files include user emails (for mapping only)
5. **SSH tunnel security** - Ensures encrypted database access

### Production Safety

1. **Always dry-run first** - Validates before making changes
2. **Transaction safety** - Rollback on failure prevents partial imports
3. **Idempotent imports** - Safe to re-run with same data
4. **Password rotation** - Consider rotating credentials after migrations

### Credential Management

All credentials come from `.env.local`:

```bash
# Required for production access
POSTGRES_PASSWORD_PRODUCTION=your-secure-password

# Required for local access
POSTGRES_PASSWORD=localpass

# Optional for staging
POSTGRES_PASSWORD_STAGING=staging-password
```

## Advanced Usage

### Custom Config Directory

```bash
python -m database.collection_transfer.export_collections \
  --config-dir /path/to/custom/configs \
  --collection-name "Test"
```

### Export by UUID

```bash
python -m database.collection_transfer.export_collections \
  --collection-id "550e8400-e29b-41d4-a716-446655440000" \
  --source-env local
```

### Skip Embeddings for Faster Transfer

```bash
python -m database.collection_transfer.export_collections \
  --collection-name "Large Collection" \
  --no-embeddings
```

Note: You'll need to re-process documents to generate embeddings after import.

## Makefile Commands Reference

```bash
# Export
make export-collection ENV=local                          # Export all from environment
make export-collection NAME="collection" ENV=local        # Export specific collection

# Import
make import-collection FILE=file.json ENV=production DRY_RUN=true  # Dry-run
make import-collection FILE=file.json ENV=production               # Actual import
```

## File Structure

```
database/
├── collection_transfer/
│   ├── README.md                    # This file
│   ├── __init__.py                  # Package initialization
│   ├── config.py                    # Configuration loader
│   ├── user_mapper.py               # User ID mapping logic
│   ├── export_collections.py        # Export script
│   ├── import_collections.py        # Import script
│   ├── test_prod_connection.py      # Test utility (checks connection + lists users)
│   └── tunnel_to_production.sh      # SSH tunnel helper (requires configuration)
├── transfer_configs/
│   ├── environments.yml             # Database configs (NO PASSWORDS)
│   └── user_mappings.yml            # User mapping rules (NO PASSWORDS)
└── exports/
    └── *.json                       # Export files (gitignored, never commit)
```

## Dependencies

Automatically installed via Poetry:
- `psycopg2-binary` - PostgreSQL adapter
- `pyyaml` - YAML configuration parsing

## License

Part of the Agent Platform - see main project LICENSE.
