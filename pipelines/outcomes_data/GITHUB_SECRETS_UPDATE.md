# GitHub Secrets Update Required

After deploying the updated `docker-compose.production.yml` that exposes the PostgreSQL port, you need to update the GitHub secrets to use the direct database connection.

## Updated GitHub Secrets

Go to: `Settings → Secrets and variables → Actions`

Update the following secrets:

| Secret Name | New Value | Notes |
|------------|-----------|-------|
| `PROD_POOLER_HOST` | `e18-apps.com` | Main domain (direct to server) |
| `PROD_POOLER_PORT` | `5432` | Standard PostgreSQL port (now exposed) |
| `PROD_DB_PASSWORD` | `Pr0ducti0nP4ss` | *(keep existing)* |
| `PROD_TENANT_ID` | *(empty/delete)* | Not needed for direct connection |
| `PROD_DB_NAME` | `postgres` | *(keep existing)* |
| `PROD_DB_USER` | `postgres` | *(keep existing)* |

## What Changed

**Before:**
- Attempted to connect via Supavisor pooler through Caddy on port 443
- Pooler not exposed externally → connection failed

**After:**
- Direct PostgreSQL connection on port 5432
- Database port exposed in `docker-compose.production.yml`
- No pooler/tenant configuration needed

## Connection String

The workflow will construct:
```
postgres://postgres:{PASSWORD}@e18-apps.com:5432/postgres
```

## Security Note

Exposing port 5432 allows external connections to your database. Ensure:
1. Strong password is configured (`POSTGRES_PASSWORD` in production `.env`)
2. Firewall rules are properly configured
3. Regular security audits

## Testing

After updating secrets and deploying:

```bash
# Test locally first
cd pipelines/outcomes_data
source .env.production
poetry run outcomes-data test-db

# Then trigger GitHub Actions workflow
gh workflow run outcomes-data-pipeline.yml --ref main -f command=refresh_latest
```
