# NHS Data Pipeline: Quick Debugging Guide

## Quick Reference: Where to Check for Discrepancies

### 1. Verify Treatment Stage Filtering (Metric 5)

The most critical check for cancer 31-day (metric 5) discrepancies.

**Check source CSV**:
```bash
cd /Users/lucelsby/Documents/repos/e18/e18-agent-os
# Find latest cancer metric 5 CSV in cache
find pipelines/outcomes_data -name "*5*.csv" -type f -mtime -1 | head -5

# Open and inspect
less <CSV_PATH>
# Look for rows with treatment_stage or stageroute column values:
# - "ALL STAGES"
# - "FIRST TREATMENTS" 
# - "SUBSEQUENT TREATMENTS"
```

**The Code that filters this** (transforms.py lines 177-182):
```python
# For metric 5 (31-day): Filter to "ALL STAGES" rows ONLY
if metric_val == 5 and treatment_stage_col and treatment_stage_col in df.columns:
    df = df[df[treatment_stage_col].str.upper().str.strip() == "ALL STAGES"].copy()
```

If this filter isn't working correctly, you'll get wrong percentages.

---

### 2. Check Database Aggregation

**Query**: What's actually in the database?

```sql
-- Connect to Supabase database
psql "postgresql://postgres:PASSWORD@db.supabase.co:5432/postgres"

-- Check what cancer metrics are stored for a specific org
SELECT 
  period, metric, cancer_type, referral_route,
  within_target, outside_target, pct_within_target,
  (within_target / (within_target + outside_target)) as calculated_pct
FROM performance_data.cancer_target_metrics
WHERE org_code = 'RJ1'  -- Example trust code
  AND metric = 5
  AND period = '2025-08'
ORDER BY cancer_type, referral_route;

-- Check if trust-level aggregates exist (cancer_type IS NULL)
SELECT 
  org_code, period, metric, cancer_type, referral_route,
  within_target, outside_target, pct_within_target
FROM performance_data.cancer_target_metrics
WHERE cancer_type IS NULL
  AND metric = 5
  AND period = '2025-08'
LIMIT 10;
```

**What to look for**:
- Row with `cancer_type IS NULL` and `referral_route = 'ALL ROUTES'` = trust-level aggregate
- Sum of disaggregated within_target values should equal the NULL cancer_type within_target
- Percentage should be: SUM(within) / SUM(within + outside) across all rows

---

### 3. Trace Through the Views

**Step 1: metric_values_base View**
```sql
-- This view combines source data and creates aggregates
SELECT 
  metric_id, cancer_type, referral_route, org_code, period,
  numerator, denominator, value, is_rollup, rollup_method
FROM performance_data.metric_values_base
WHERE org_code = 'RJ1'
  AND metric_id = 'cancer_31d_pct_within_target'
  AND period = '2025-08'
ORDER BY cancer_type NULLS LAST, referral_route;

-- Look for:
-- - Source rows: is_rollup = FALSE, rollup_method = 'source'
-- - Trust aggregates: is_rollup = TRUE, rollup_method = 'weighted', cancer_type IS NULL
```

**Step 2: insight_metrics_long Materialized View**
```sql
-- This is what the tool actually queries
SELECT 
  metric_id, cancer_type, referral_route, org_code,
  value, numerator, denominator,
  percentile_overall, percentile_trust_type,
  is_rollup, rollup_method
FROM performance_data.insight_metrics_long
WHERE org_code = 'RJ1'
  AND metric_id = 'cancer_31d_pct_within_target'
  AND period = '2025-08'
ORDER BY cancer_type NULLS LAST;

-- The tool filters to: cancer_type IS NULL AND referral_route = 'ALL ROUTES'
-- This gives the trust-level aggregate value
```

---

### 4. Understand the Aggregation Logic

**Where does the percentage come from?**

```sql
-- Trust-level aggregates are created in metric_values_base view
-- For metric 5 (31-day), this SQL runs:

SELECT
  period,
  'cancer_31d_pct_within_target'::TEXT AS metric_id,
  org_code,
  'ALL ROUTES'::TEXT AS referral_route,
  NULL::TEXT AS cancer_type,
  SUM(within_target)::NUMERIC AS numerator,
  SUM(within_target + outside_target)::NUMERIC AS denominator,
  CASE WHEN SUM(within_target + outside_target) > 0
       THEN SUM(within_target)::NUMERIC / SUM(within_target + outside_target)::NUMERIC
       ELSE NULL END AS value
FROM cancer_target_metrics c
WHERE metric IN (5, 8)
  AND referral_route = 'ALL ROUTES'
GROUP BY period, metric, org_code;

-- This sums numerators and denominators ONLY from ALL ROUTES rows
-- Why? Disaggregated rows already include all specific routes
-- Including non-ALL ROUTES rows would double-count
```

---

### 5. Tool Query Filtering

**The exact query the tool runs**:

```python
# From queries.py, get_comprehensive_performance()
# For cancer domain without breakdown:

WHERE tm.cancer_type IS NULL
  AND (tm.referral_route = 'ALL ROUTES' OR tm.referral_route IS NULL)

# This ONLY selects trust-level aggregates
# Result: One row per metric per org per period (no disaggregation)
```

**Tool filtering code** (tools.py lines 971-976):
```python
overall_cancer_metrics = [
    m for m in metrics_by_domain['cancer']
    if m.get('cancer_type') is None and m.get('referral_route') == 'ALL ROUTES'
]
```

---

### 6. Identify the Discrepancy Type

**If you see two different numbers for the same metric:**

| Number A | Number B | Likely Cause |
|----------|----------|--------------|
| 88% (low sample) | 90.7% (high sample) | Disaggregated vs aggregated - EXPECTED |
| Same samples | Different % | Calculation/rounding error |
| Old number | New number | Database not refreshed or old data loaded |
| Trust agg | Single cancer type | Accessing wrong row in query |

**Quick diagnosis**:
```bash
# Check denominator (sample size)
SELECT 
  cancer_type,
  referral_route,
  denominator,
  value
FROM performance_data.insight_metrics_long
WHERE org_code = 'RJ1'
  AND metric_id = 'cancer_31d_pct_within_target'
  AND period = '2025-08'
ORDER BY cancer_type;

# Low denominators (<100) with ~88% = specific cancer type
# High denominators (>1000) with 90.7% = trust aggregate
```

---

### 7. Common Issues & Solutions

| Issue | Symptom | Solution |
|-------|---------|----------|
| **Materialized view stale** | Old numbers | `REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;` |
| **Wrong period selected** | Number from last month | Check `MAX(period)` for domain |
| **Treatment stage filter bug** | Metric 5 way off | Check transforms.py line 177-182 |
| **Sample size too small** | Valid_sample = FALSE but still displayed | Check `denominator >= min_denominator` |
| **Rounding inconsistency** | 0.888 vs 88.8% vs 89% | Check formatters.py format_value_with_unit() |
| **Wrong aggregation** | Double-counted patients | Check WHERE clauses in cancer_trust_aggregate CTE |

---

### 8. Testing End-to-End

**Minimal test case**:

```bash
# 1. Check raw CSV has data
grep -c "ALL STAGES" /path/to/metric5.csv

# 2. Verify it loads to silver stage
# Look at pipeline logs for row counts

# 3. Verify gold stage transforms correctly
# Check if pct_within_target = (within) / (within + outside)

# 4. Query database table
psql -c "SELECT SUM(within_target), SUM(outside_target) 
         FROM cancer_target_metrics 
         WHERE org_code='RJ1' AND metric=5"

# 5. Query view (should include aggregates)
psql -c "SELECT cancer_type, referral_route, value 
         FROM metric_values_base 
         WHERE org_code='RJ1' AND metric_id='cancer_31d_pct_within_target'"

# 6. Query materialized view (should have percentiles)
psql -c "SELECT cancer_type, referral_route, value, percentile_overall 
         FROM insight_metrics_long 
         WHERE org_code='RJ1' AND metric_id='cancer_31d_pct_within_target'"

# 7. Query tool would execute (actual filtering)
psql -c "SELECT value FROM insight_metrics_long 
         WHERE org_code='RJ1' AND metric_id='cancer_31d_pct_within_target' 
         AND cancer_type IS NULL AND referral_route = 'ALL ROUTES'"
```

---

### 9. Enable Debug Logging

**In queries.py, add logging before executing queries**:

```python
# Add around line 816-820 in get_comprehensive_performance()
logger.info(f"""
=== CANCER DOMAIN QUERY ===
Query:\n{query}
Params:
  - org_code: {query_params['org_code']}
  - period: {query_params['period']}
  - domain: {query_params['domain']}
================
""")
```

**Run with logging**:
```bash
export RUST_LOG=debug
poetry run python -m mcp_server.main --transport http
```

---

### 10. Validate with NHS Official Data

**Cross-check with NHS England published metrics**:
- Visit: [NHS England Cancer Waiting Times Statistics](https://www.england.nhs.uk/statistics/statistical-work-areas/cancer-waiting-times/)
- Download "All metrics" spreadsheet for same period
- Find trust's 31-day metric value
- Compare with database value

**If they match**: Your data load and transforms are correct
**If they don't match**: Issue is in extraction/transformation stage

---

## Key Files to Modify

| File | What to Check | Lines |
|------|---------------|-------|
| `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py` | Treatment stage filter | 177-182 |
| `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py` | Percentage calculation | 196-235 |
| `database/migrations/client_specific/005_add_cancer_trust_aggregates.sql` | Trust aggregation logic | 199-223 |
| `apps/mcp/src/mcp_server/tools/nhs_analytics/queries.py` | Cancer filtering in tool | 785-795 |
| `apps/mcp/src/mcp_server/tools/nhs_analytics/tools.py` | Metric display | 971-1007 |

---

## Quick Commands

```bash
# Start from repo root
cd /Users/lucelsby/Documents/repos/e18/e18-agent-os

# Connect to database
psql "postgresql://postgres:PASSWORD@db.supabase.co:5432/postgres"

# Refresh materialized view
psql -c "REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;"

# Count rows in table
psql -c "SELECT metric, COUNT(*) FROM cancer_target_metrics WHERE period='2025-08' GROUP BY metric;"

# Find latest period per metric
psql -c "SELECT metric, MAX(period) FROM cancer_target_metrics GROUP BY metric;"

# Check trust codes
psql -c "SELECT DISTINCT org_code FROM dim_organisations LIMIT 20;"
```

---

## Summary Checklist

Before declaring a discrepancy "fixed", verify:

- [ ] Source CSV contains expected "ALL STAGES" data
- [ ] Silver stage correctly filters ODS codes
- [ ] Gold stage filters to "ALL STAGES" for metric 5
- [ ] Percentages recalculated correctly: pct = within / (within + outside)
- [ ] Trust aggregates created with cancer_type IS NULL
- [ ] Aggregates sum ONLY "ALL ROUTES" rows (not double-counting)
- [ ] Database rows match calculated values (spot-check 3-5 rows)
- [ ] metric_values_base view includes both source and aggregate rows
- [ ] insight_metrics_long materialized view is refreshed
- [ ] Tool query filters to cancer_type IS NULL and referral_route = 'ALL ROUTES'
- [ ] Percentiles calculated in correct cohort (disagg_key)
- [ ] Output matches NHS England official published data

