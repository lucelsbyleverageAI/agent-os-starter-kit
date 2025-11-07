# Collection Transfer Setup Guide

Quick guide to configure the collection transfer tool for your environments.

## Step 1: Update environments.yml

1. Open `database/transfer_configs/environments.yml`
2. Update the production database connection details:

```yaml
production:
  host: your-production-db-hostname.com  # Update this
  port: 5432
  database: postgres
  user: postgres
  description: "Production database"
```

If you have a staging environment, add it:

```yaml
staging:
  host: your-staging-db-hostname.com
  port: 5432
  database: postgres
  user: postgres
  description: "Staging database"
```

## Step 2: Update user_mappings.yml

1. Open `database/transfer_configs/user_mappings.yml`
2. Update the `default_owners` section with your actual admin emails:

```yaml
default_owners:
  local: "your-local-admin@localhost"      # Your local admin email
  production: "your-prod-admin@example.com" # Your production admin email
```

3. (Optional) Add explicit email mappings if you know users exist in both environments:

```yaml
email_mappings:
  - email: your-email@example.com
    description: "Your name (dev admin)"
  - email: team-member@example.com
    description: "Team member"
```

## Step 3: Set Database Passwords

Set environment variables for your database passwords:

```bash
# For local development
export POSTGRES_PASSWORD="your-local-db-password"

# For production (optional: can use environment-specific)
export POSTGRES_PASSWORD_PRODUCTION="your-production-db-password"
```

**Tip**: Add these to your `.env.local` file or shell profile for persistence.

## Step 4: Install Dependencies

```bash
# Install PyYAML and other dependencies
poetry install
```

## Step 5: Test the Configuration

Test that the configuration is correct:

```bash
# Test export from local (dry-run)
python database/collection_transfer/export_collections.py \
  --all \
  --source-env local \
  --output /tmp/test_export.json

# If you see collections listed, configuration is correct!
```

## Step 6: Ready to Use!

You're now ready to migrate collections between environments. See the main README for usage examples:

```bash
# Export a collection
make export-collection NAME="My Collection"

# Import to production (with validation first)
make import-collection FILE=database/exports/my_collection_*.json ENV=production DRY_RUN=true
make import-collection FILE=database/exports/my_collection_*.json ENV=production
```

## Troubleshooting

### "Environment 'production' not found"
- Check that you've updated `environments.yml` with your production settings
- Make sure the YAML syntax is correct (proper indentation)

### "Database password not found"
- Set the `POSTGRES_PASSWORD` or `POSTGRES_PASSWORD_PRODUCTION` environment variable
- Or add to your `.env.local` file

### "Connection refused"
- For production: Make sure you can reach the production database from your local machine
- You may need VPN access or SSH tunneling
- For local: Make sure your Docker containers are running (`make start-dev`)

## Security Checklist

- [ ] Never commit `environments.yml` with production passwords
- [ ] Never commit export files (they contain actual data)
- [ ] Use strong passwords for production databases
- [ ] Consider using `.pgpass` file for password management
- [ ] Review user permissions before importing to production

## Next Steps

See `database/collection_transfer/README.md` for:
- Detailed usage examples
- User mapping strategies
- Troubleshooting guide
- Advanced features
