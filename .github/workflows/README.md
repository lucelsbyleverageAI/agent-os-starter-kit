# GitHub Actions Workflows

## NHS Outcomes Data Pipeline

**File**: `outcomes-data-pipeline.yml`

Automated workflow that refreshes NHS England performance data in your production database.

### What It Does

Runs the outcomes data pipeline to fetch and process:
- **RTT (Referral to Treatment)** waiting times data
- **Cancer Waiting Times** performance metrics (28-day, 31-day, 62-day)
- **NHS Oversight Framework** trust performance data

Data is processed through Bronze → Silver → Gold layers and loaded into the `performance_data` schema in your Supabase database.

### Schedule

**Automatic runs**: 15th of each month at 2am UTC

This timing ensures NHS England has published the latest monthly data (typically released 10-14 days after month-end).

### Manual Triggers

You can also run the pipeline manually:

1. Go to **Actions** → **NHS Outcomes Data Pipeline**
2. Click **Run workflow**
3. Select options:

#### Command Options

- **`refresh_latest`** (default) - Process only the latest period for each data source
  - Use for: Monthly updates
  - Duration: ~5-10 minutes
  - Data volume: ~20,000 rows

- **`backfill`** - Process historical data from a start period to present
  - Use for: Initial load or recovering missing periods
  - Duration: ~30-120 minutes (depending on start period)
  - Data volume: ~1-2 million rows (from 2015-10)
  - **Important**: Specify `start_period` (e.g., `2015-10`)

- **`rtt_only`** - Process only RTT data
  - Use for: Fixing RTT data issues
  - Duration: ~2-5 minutes

- **`cancer_only`** - Process only Cancer data
  - Use for: Fixing Cancer data issues
  - Duration: ~3-7 minutes

- **`oversight_only`** - Process only Oversight Framework data
  - Use for: Quarterly oversight updates
  - Duration: ~1-2 minutes

#### Other Options

- **`start_period`** - Required for backfill command (format: `YYYY-MM`, e.g., `2015-10`)
- **`refresh_views`** - Refresh materialized views after pipeline (default: `true`)

### Required GitHub Secrets

Configure these in **Settings** → **Secrets and variables** → **Actions**:

| Secret Name | Description | Example |
|------------|-------------|---------|
| `PROD_POOLER_HOST` | Supabase pooler hostname | `aws-0-us-east-1.pooler.supabase.com` |
| `PROD_POOLER_PORT` | Supabase pooler port | `6543` |
| `PROD_DB_PASSWORD` | Production database password | `your-secure-password` |
| `PROD_TENANT_ID` | Supabase tenant ID | `your-project-ref` |
| `PROD_DB_NAME` (optional) | Database name | `postgres` (default) |
| `PROD_DB_USER` (optional) | Database user | `postgres` (default) |

#### How to Get These Values

**From Supabase Dashboard**:

1. Go to your project → **Settings** → **Database**
2. Scroll to **Connection pooling** section
3. Copy the connection string (mode: Transaction)
4. Extract values:
   ```
   postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres
                          ↑             ↑                ↑                               ↑
                    TENANT_ID    PASSWORD      POOLER_HOST                       POOLER_PORT
   ```

### Initial Setup (One-Time)

After configuring secrets, run the initial historical backfill:

1. Go to **Actions** → **NHS Outcomes Data Pipeline**
2. Click **Run workflow**
3. Select:
   - Command: **`backfill`**
   - Start period: **`2015-10`** (or your preferred start date)
   - Refresh views: **`true`**
4. Click **Run workflow**

This will populate ~10 years of historical data (takes ~1-2 hours).

### Monitoring

#### Success Indicators

- Workflow shows green checkmark ✅
- Job summary shows dataset statistics
- Materialized view refresh completes
- Row counts increase in database

#### Failure Handling

If the workflow fails:

1. **Automatic**: An issue is created in the repo with failure details
2. **Manual**: Check the workflow logs for error messages
3. Common fixes:
   - Verify secrets are configured correctly
   - Check production database is accessible
   - Ensure NHS England website structure hasn't changed
   - Review pipeline.log artifact for detailed errors

#### Logs and Artifacts

- **Pipeline logs** are uploaded as artifacts (retained for 30 days)
- **Summary statistics** show in job output
- **Materialized view row counts** displayed after refresh

### Data Refresh Strategy

#### Monthly Automatic Refresh (Recommended)

Let the scheduled workflow run automatically on the 15th:

```yaml
schedule:
  - cron: '0 2 15 * *'  # 15th of each month at 2am UTC
```

This will:
1. Fetch latest RTT data (~2,500 rows)
2. Fetch latest Cancer data (~8,500 rows)
3. Fetch latest Oversight data (~9,500 rows)
4. Refresh materialized views with new data

#### Quarterly Oversight Updates

NHS Oversight Framework updates quarterly. When new data is published:

1. Update oversight CSV URLs in `.env.example` (or secrets)
2. Manually trigger `oversight_only` workflow

#### Handling Late Publications

If NHS data is published late (after the 15th):

1. Manually trigger `refresh_latest` workflow
2. Or wait for next month's scheduled run

### Quarterly Maintenance

**Every quarter** (when NHS Oversight Framework updates):

1. Check NHS England for new oversight CSV URLs
2. Update URLs in `pipelines/outcomes_data/outcomes_data/core/config.py`:
   - `oversight_metrics_acute`
   - `oversight_metrics_non_acute`
   - `oversight_metrics_ambulance`
   - `oversight_league_table_acute`
   - `oversight_league_table_non_acute`
   - `oversight_league_table_ambulance`
3. Commit changes
4. Workflow will use new URLs on next run

### Caching

The workflow caches:

1. **Poetry dependencies** - Speeds up dependency installation
2. **NHS data downloads** - Reduces redundant downloads from NHS England
3. Cache is workspace-scoped and persists across runs

### Troubleshooting

#### "Connection failed" Error

**Cause**: Database credentials incorrect or database unreachable

**Fix**:
1. Verify secrets are correct
2. Check Supabase project is running
3. Test connection locally:
   ```bash
   cd pipelines/outcomes_data
   poetry run outcomes-data test-db
   ```

#### "No data discovered" Warning

**Cause**: NHS England website structure changed

**Fix**:
1. Check RTT scraper: `outcomes_data/data_sources/rtt/scraper.py`
2. Check Cancer scraper: `outcomes_data/data_sources/cancer/scraper.py`
3. Update selectors if NHS website changed

#### Materialized View Refresh Timeout

**Cause**: Too much data, slow database

**Fix**:
1. Increase workflow timeout (currently 180 minutes)
2. Or refresh view manually after workflow completes

### Cost Considerations

**GitHub Actions**: Free for public repos, 2,000 minutes/month for private repos

**Estimated usage**:
- Monthly refresh: ~10 minutes
- Annual cost: ~120 minutes (well within free tier)

**Backfill**: ~120 minutes (one-time, counts toward monthly limit)

### Example Workflows

#### Monthly Routine

```
15th of month, 2am UTC
↓
Workflow triggers automatically
↓
Fetches latest data from NHS England
↓
Processes Bronze → Silver → Gold
↓
Upserts to production database
↓
Refreshes materialized views
↓
Posts summary to job output
```

#### Recovering Missing Data

```
Manual trigger
↓
Command: backfill
Start: 2024-01 (missing month)
↓
Processes all periods from 2024-01 to present
↓
Fills gaps in database
↓
Refreshes views
```

### Support

For issues with:
- **Pipeline logic**: Check `pipelines/outcomes_data/` code
- **Workflow**: Check `.github/workflows/outcomes-data-pipeline.yml`
- **NHS data sources**: Check `outcomes_data/data_sources/` scrapers
- **Database schema**: Check `database/migrations/client_specific/002_performance_data_init.sql`

### Related Documentation

- Pipeline architecture: `pipelines/outcomes_data/DATA_OVERVIEW.md`
- Database schema: `database/migrations/client_specific/002_performance_data_init.sql`
- Configuration: `pipelines/outcomes_data/outcomes_data/core/config.py`
