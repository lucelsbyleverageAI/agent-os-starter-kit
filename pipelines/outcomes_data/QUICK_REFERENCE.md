# NHS Outcomes Data Pipeline - Quick Reference

## Local Development Commands

### Setup
```bash
cd pipelines/outcomes_data
poetry install
cp .env.example .env  # Edit with your local DB credentials
```

### Test Database Connection
```bash
poetry run outcomes-data test-db
```

### Run Pipelines

#### All Data Sources

```bash
# Latest period only (~5-10 min)
poetry run outcomes-data run-all

# Full historical backfill from Oct 2015 (~30-120 min)
poetry run outcomes-data run-all --start 2015-10

# Backfill from specific date
poetry run outcomes-data run-all --start 2023-01
```

#### RTT (Referral to Treatment)

```bash
# Latest period only
poetry run outcomes-data rtt refresh-latest

# Full backfill from Oct 2015
poetry run outcomes-data rtt backfill --start 2015-10

# Specific month
poetry run outcomes-data rtt rebuild-month 2024-12
```

#### Cancer Waiting Times

```bash
# Latest period (all 3 metrics: 28d, 31d, 62d)
poetry run outcomes-data cancer refresh-latest

# Full backfill
poetry run outcomes-data cancer backfill --start 2015-10

# Specific month
poetry run outcomes-data cancer rebuild-month 2024-12
```

#### Oversight Framework

```bash
# Run full pipeline (downloads latest snapshot)
poetry run outcomes-data oversight run
```

#### ODS (Organisation Data Service)

```bash
# Sync organizations (default: NHS TRUST + NHS TRUST SITE)
poetry run outcomes-data ods sync

# Sync specific role codes
poetry run outcomes-data ods sync --role-code RO197 --role-code RO198
```

### Refresh Materialized Views (After Load)

```bash
# Using local Supabase
docker exec supabase-db psql -U postgres -d postgres -c \
  "REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;"
```

## GitHub Actions Workflow

### Manual Trigger

1. Go to **Actions** → **NHS Outcomes Data Pipeline**
2. Click **Run workflow**
3. Select options:

### Command Options

| Command | Use Case | Duration | Data Volume |
|---------|----------|----------|-------------|
| `refresh_latest` | Monthly updates | ~5-10 min | ~20k rows |
| `backfill` | Initial load / Recovery | ~30-120 min | ~1-2M rows |
| `rtt_only` | Fix RTT issues | ~2-5 min | ~2.5k rows |
| `cancer_only` | Fix Cancer issues | ~3-7 min | ~8.5k rows |
| `oversight_only` | Quarterly updates | ~1-2 min | ~10k rows |

### When to Use Each Command

**`refresh_latest`** (Default - Monthly)
- Scheduled run on 15th of month
- Quick update with latest NHS data
- Use after: Monthly data publication

**`backfill`**
- Initial setup (run once)
- Recovering missing periods
- Use after: Setting up new environment, detecting gaps

**`{source}_only`**
- Specific data source issues
- Testing individual pipelines
- Use after: Source-specific errors, selective updates

## Data Publication Schedule

| Data Source | Frequency | Typical Publication Date |
|-------------|-----------|-------------------------|
| RTT | Monthly | 11-13 days after month-end |
| Cancer (Provisional) | Monthly | ~2 weeks after month-end |
| Cancer (Final) | Monthly | ~6 weeks after month-end |
| Oversight Framework | Quarterly | Mid-quarter month |

## Database Quick Checks

### Row Counts by Dataset

```sql
SELECT
  'RTT' as dataset,
  COUNT(*) as total_rows,
  COUNT(DISTINCT period) as periods,
  MIN(period) as earliest,
  MAX(period) as latest
FROM performance_data.rtt_metrics_gold

UNION ALL

SELECT
  'Cancer',
  COUNT(*),
  COUNT(DISTINCT period),
  MIN(period),
  MAX(period)
FROM performance_data.cancer_target_metrics

UNION ALL

SELECT
  'Oversight',
  COUNT(*),
  COUNT(DISTINCT reporting_date),
  MIN(reporting_date),
  MAX(reporting_date)
FROM performance_data.oversight_metrics_raw;
```

### Check Materialized View Status

```sql
SELECT
  schemaname,
  matviewname,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||matviewname)) as size,
  last_refresh
FROM pg_matviews
WHERE schemaname = 'performance_data';
```

### Latest Data by Organization

```sql
-- Latest RTT data for a specific trust (e.g., RJ1 - Guy's and St Thomas')
SELECT
  period,
  org_code,
  org_name,
  rtt_part_type,
  compliance_18w,
  waiting_list_total
FROM performance_data.rtt_metrics_gold
WHERE org_code = 'RJ1'
ORDER BY period DESC
LIMIT 10;
```

### Insight Metrics Summary

```sql
-- Count of metrics per trust in latest period
SELECT
  org_code,
  org_name,
  COUNT(DISTINCT metric_id) as metric_count,
  MAX(period) as latest_period
FROM performance_data.insight_metrics_latest
GROUP BY org_code, org_name
ORDER BY metric_count DESC
LIMIT 10;
```

## Expected Data Volumes

### After Full Backfill (2015-10 to Present)

| Table | Rows | Periods | Size |
|-------|------|---------|------|
| rtt_metrics_gold | ~300,000 | ~120 | ~50 MB |
| cancer_target_metrics | ~1,000,000 | ~120 | ~150 MB |
| oversight_metrics_raw | ~10,000 | ~15 | ~2 MB |
| oversight_league_table_raw | ~3,000 | ~15 | ~500 KB |
| dim_organisations | ~200 | - | ~50 KB |
| **insight_metrics_long** | ~1,500,000 | ~120 | ~250 MB |

### Per Month (Incremental)

| Table | New Rows/Month |
|-------|----------------|
| rtt_metrics_gold | ~2,500 |
| cancer_target_metrics | ~8,500 |
| oversight_metrics_raw | ~600 (quarterly) |
| insight_metrics_long | ~12,000 |

## Common Issues & Quick Fixes

### "Connection failed"

```bash
# Test connection
poetry run outcomes-data test-db

# Check environment variables
echo $POSTGRES_HOST
echo $POSTGRES_PORT
echo $POSTGRES_PASSWORD

# Verify Docker container is running
docker ps | grep supabase-db
```

### "No data discovered"

```bash
# Check NHS England website is accessible
curl -I https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/

# Enable debug logging
export LOG_LEVEL=DEBUG
poetry run outcomes-data rtt refresh-latest
```

### Stale Materialized View

```bash
# Check last refresh time
docker exec supabase-db psql -U postgres -d postgres -c \
  "SELECT matviewname, last_refresh FROM pg_matviews WHERE schemaname='performance_data';"

# Force refresh
docker exec supabase-db psql -U postgres -d postgres -c \
  "REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;"
```

### Cache Issues

```bash
# Clear download cache
rm -rf pipelines/outcomes_data/.cache

# Run with fresh downloads
poetry run outcomes-data run-all
```

## File Locations

| Component | Path |
|-----------|------|
| CLI Entry Point | `pipelines/outcomes_data/outcomes_data/cli.py` |
| Configuration | `pipelines/outcomes_data/outcomes_data/core/config.py` |
| Database Writer | `pipelines/outcomes_data/outcomes_data/core/database.py` |
| RTT Pipeline | `pipelines/outcomes_data/outcomes_data/data_sources/rtt/pipeline.py` |
| Cancer Pipeline | `pipelines/outcomes_data/outcomes_data/data_sources/cancer/pipeline.py` |
| Oversight Pipeline | `pipelines/outcomes_data/outcomes_data/data_sources/oversight/pipeline.py` |
| GitHub Workflow | `.github/workflows/outcomes-data-pipeline.yml` |
| Database Migration | `database/migrations/client_specific/002_performance_data_init.sql` |

## Environment Variables

### Local Development (.env)

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5434
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=localpass

CACHE_ROOT=.cache
HTTP_TIMEOUT_S=60
HTTP_RETRIES=3
LOG_LEVEL=INFO
```

### Production (GitHub Secrets)

- `PROD_POOLER_HOST` - Supabase pooler hostname
- `PROD_POOLER_PORT` - Pooler port (typically 6543)
- `PROD_DB_PASSWORD` - Database password
- `PROD_TENANT_ID` - Supabase tenant ID

## Metric IDs

### RTT Metrics (5)

- `rtt_pct_within_18` - % within 18 weeks (stock)
- `rtt_pct_over_52` - % over 52 weeks (stock)
- `rtt_p92_weeks_waiting` - 92nd percentile weeks (stock)
- `rtt_compliance_18w` - % within 18 weeks (flow)
- `rtt_unknown_clock_start_rate` - % unknown clock start

### Cancer Metrics (6)

- `cancer_28d_pct_within_target` - 28-day FDS
- `cancer_31d_pct_within_target` - 31-day first treatment
- `cancer_62d_pct_within_target` - 62-day referral to treatment
- `cancer_28d_gap_usc_all` - 28-day USC gap
- `cancer_31d_gap_usc_all` - 31-day USC gap
- `cancer_62d_gap_usc_all` - 62-day USC gap

### Oversight Metrics (20+)

- `oversight_average_score` - Composite oversight score
- `oversight_segment_inverse` - Segment (higher is better)
- Plus 20+ individual domain metrics from raw table

## Support

- **Pipeline Documentation**: `pipelines/outcomes_data/DATA_OVERVIEW.md`
- **Workflow Setup**: `.github/workflows/SETUP_CHECKLIST.md`
- **Workflow Docs**: `.github/workflows/README.md`
- **Database Schema**: `database/migrations/client_specific/002_performance_data_init.sql`

---

**Last Updated**: 2025-10-28
