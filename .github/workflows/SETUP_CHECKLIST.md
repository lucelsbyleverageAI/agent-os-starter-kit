# NHS Outcomes Data Pipeline - Setup Checklist

Use this checklist to set up the automated pipeline for the first time.

## Prerequisites

- [ ] Production Supabase database is running
- [ ] You have admin access to the GitHub repository
- [ ] You have access to Supabase project settings

## Step 1: Configure GitHub Secrets

### 1.1 Navigate to Secrets

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

### 1.2 Get Supabase Connection Details

1. Open [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your production project
3. Go to **Settings** → **Database**
4. Scroll to **Connection pooling** section
5. Select **Transaction** mode
6. Copy the connection string

Example:
```
postgresql://postgres.abcdefghijklmnop:your_password@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

### 1.3 Create Secrets

Create these secrets one by one:

- [ ] **`PROD_POOLER_HOST`**
  - Value: `aws-0-us-east-1.pooler.supabase.com` (from connection string)
  - Example: The part between `@` and `:6543`

- [ ] **`PROD_POOLER_PORT`**
  - Value: `6543` (from connection string)
  - Example: The number after the hostname

- [ ] **`PROD_DB_PASSWORD`**
  - Value: Your database password (from connection string)
  - Example: The part between `:` and `@` (after `postgres.PROJECT_REF:`)
  - ⚠️ Keep this secure!

- [ ] **`PROD_TENANT_ID`**
  - Value: Your project reference (from connection string)
  - Example: The part after `postgres.` and before the password
  - Example: `abcdefghijklmnop`

- [ ] **`PROD_DB_NAME`** (Optional, defaults to `postgres`)
  - Value: `postgres`
  - Only set if using a different database name

- [ ] **`PROD_DB_USER`** (Optional, defaults to `postgres`)
  - Value: `postgres`
  - Only set if using a different user

## Step 2: Verify Database Schema

The pipeline requires the `performance_data` schema and tables to exist.

- [ ] Check migration has run in production:

```sql
-- Run this in Supabase SQL Editor
SELECT tablename
FROM pg_tables
WHERE schemaname = 'performance_data'
ORDER BY tablename;
```

Expected tables:
- `cancer_target_metrics`
- `dim_organisations`
- `metric_catalogue`
- `ods_org_current`
- `oversight_league_table_raw`
- `oversight_metrics_raw`
- `rtt_metrics_gold`

- [ ] If tables don't exist, run migration:
  - Execute `database/migrations/client_specific/002_performance_data_init.sql`
  - Execute `database/migrations/client_specific/004_add_comprehensive_oversight_metrics.sql`

## Step 3: Test the Workflow (Dry Run)

Before running a full backfill, test with a single recent month:

- [ ] Go to **Actions** → **NHS Outcomes Data Pipeline**
- [ ] Click **Run workflow**
- [ ] Configure:
  - Branch: `main`
  - Command: `refresh_latest`
  - Refresh views: `true`
- [ ] Click **Run workflow**
- [ ] Wait for completion (~5-10 minutes)
- [ ] Verify success:
  - [ ] Workflow shows green checkmark ✅
  - [ ] Check job summary for statistics
  - [ ] Verify data in database:

```sql
-- Check row counts
SELECT
  'RTT' as dataset,
  COUNT(*) as rows,
  MAX(period) as latest_period
FROM performance_data.rtt_metrics_gold

UNION ALL

SELECT
  'Cancer',
  COUNT(*),
  MAX(period)
FROM performance_data.cancer_target_metrics

UNION ALL

SELECT
  'Oversight',
  COUNT(*),
  MAX(reporting_date)
FROM performance_data.oversight_metrics_raw;
```

## Step 4: Initial Historical Backfill

Once the test succeeds, load all historical data:

- [ ] Go to **Actions** → **NHS Outcomes Data Pipeline**
- [ ] Click **Run workflow**
- [ ] Configure:
  - Branch: `main`
  - Command: `backfill`
  - Start period: `2015-10` (or your preferred start)
  - Refresh views: `true`
- [ ] Click **Run workflow**
- [ ] Monitor progress (~1-2 hours)
- [ ] Verify completion:
  - [ ] Workflow completes successfully
  - [ ] Check row counts increased significantly
  - [ ] Materialized view was refreshed

Expected data volumes after backfill from 2015-10:
- RTT: ~300,000 rows
- Cancer: ~1,000,000 rows
- Oversight: ~10,000 rows
- Organizations: ~200 rows

## Step 5: Verify Scheduled Runs

- [ ] Check the workflow schedule:
  - Open `.github/workflows/outcomes-data-pipeline.yml`
  - Verify schedule: `cron: '0 2 15 * *'` (15th of each month at 2am UTC)

- [ ] Wait for first scheduled run (or manually test by changing cron to run soon)

- [ ] After first scheduled run:
  - [ ] Verify it completed successfully
  - [ ] Check data was updated for the new month
  - [ ] No issues were created (indicating no failures)

## Step 6: Set Up Monitoring (Optional)

### 6.1 Enable Email Notifications

- [ ] Go to your GitHub profile → **Settings** → **Notifications**
- [ ] Enable **Actions** notifications
- [ ] Choose email preference

### 6.2 Set Up Slack/Discord Webhook (Advanced)

If you want notifications in Slack/Discord:

1. Create a webhook in your Slack/Discord
2. Add webhook URL as GitHub secret: `SLACK_WEBHOOK_URL`
3. Modify workflow to add notification step:

```yaml
- name: Notify Slack
  if: always()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    payload: |
      {
        "text": "Pipeline ${{ job.status }}: ${{ github.workflow }}"
      }
```

## Step 7: Document Quarterly Maintenance

Set a quarterly reminder to:

- [ ] Check for new NHS Oversight Framework CSV URLs
- [ ] Update URLs in code if changed
- [ ] Run `oversight_only` workflow to refresh

## Troubleshooting

### Issue: "Connection failed" error

**Check:**
- [ ] Secrets are configured correctly (no typos)
- [ ] Production database is accessible from GitHub Actions (not firewalled)
- [ ] Password is correct and not expired

**Test locally:**
```bash
cd pipelines/outcomes_data
# Set environment variables from secrets
export POSTGRES_HOST="your-pooler-host"
export POSTGRES_PORT="6543"
export POSTGRES_PASSWORD="your-password"
export POOLER_TENANT_ID="your-tenant-id"

poetry run outcomes-data test-db
```

### Issue: "No data discovered" warning

**Check:**
- [ ] NHS England website is accessible
- [ ] Website structure hasn't changed (check scrapers)
- [ ] Network connectivity in GitHub Actions

### Issue: Workflow times out

**Solutions:**
- [ ] Increase timeout in workflow (currently 180 minutes)
- [ ] Run backfill in smaller chunks (e.g., 5-year periods)
- [ ] Check database performance

## Completion Checklist

- [ ] All secrets configured
- [ ] Test workflow completed successfully
- [ ] Initial backfill completed successfully
- [ ] Data verified in database
- [ ] Scheduled run tested
- [ ] Monitoring configured
- [ ] Team notified of automation

## Next Steps

Now that the pipeline is set up:

1. **Monthly**: Workflow runs automatically on the 15th
2. **Quarterly**: Update Oversight Framework URLs when NHS publishes new data
3. **Monitor**: Check workflow runs for failures
4. **Maintain**: Update scrapers if NHS website structure changes

## Support

If you encounter issues:

1. Check workflow logs in GitHub Actions
2. Review `pipeline.log` artifact
3. Consult `DATA_OVERVIEW.md` for data structure details
4. Review scraper code in `pipelines/outcomes_data/outcomes_data/data_sources/`

---

**Setup Date**: _______________
**Completed By**: _______________
**Production Database**: _______________
**Initial Backfill Start Period**: _______________
