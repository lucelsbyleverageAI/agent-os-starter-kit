# NHS Outcomes Data Pipeline: Comprehensive Analysis

## Executive Summary

This document provides a complete analysis of the NHS outcomes data pipeline, tracing data flow from source extraction through transformation, database storage, and tool output. The pipeline processes three key domains:

1. **Cancer Waiting Times** (28-day, 31-day, 62-day standards)
2. **RTT (Referral to Treatment)** waiting times
3. **Oversight Framework** metrics

### Key Finding: Primary Source of Discrepancies

The example showing 88% vs 90.7% for cancer 31-day metric likely stems from **different aggregation levels**:
- **88%**: Probably a disaggregated metric (specific cancer type or referral route)
- **90.7%**: Trust-level aggregate across all cancer types (official NHS reporting)

---

## 1. DATA EXTRACTION & PIPELINE STRUCTURE

### 1.1 Cancer Data Pipeline

#### Source Files
- **Location**: NHS England Cancer Waiting Times Statistics website (monthly updates)
- **Scraper**: `pipelines/outcomes_data/outcomes_data/data_sources/cancer/scraper.py`
- **Format**: CSV files with multi-level headers (row-based hierarchy)

#### Metric Discovery
The scraper (`CancerSourceScraper`) automatically discovers:
- Year pages: `2024-10-monthly-cancer-waiting-times-statistics/`
- Period pages: `cancer-waiting-times-for-[month]-YYYY-MM-[provisional|final]/`
- CSV files matching pattern: `[3|5|8]*.csv` (metrics 3, 5, 8)

**Key Logic** (lines 102-130 in scraper.py):
- Prioritizes **final** versions over provisional
- Maintains latest period for each metric
- Returns sorted list for processing

#### Three Metrics
| Metric | Standard | Description |
|--------|----------|-------------|
| **3** | 28-day | Faster Diagnosis Standard (75% target) |
| **5** | 31-day | Decision to Treat to Treatment (96% target) |
| **8** | 62-day | Urgent Referral to Treatment (85% target) |

---

### 1.2 Cancer Data Transformation Pipeline (Bronze→Silver→Gold)

#### Stage 1: Bronze (Raw CSV Loading)
**File**: `pipelines/outcomes_data/outcomes_data/data_sources/cancer/extractor.py`

**Process** (lines 18-80):
1. **Encoding Detection**: Uses `chardet` to detect file encoding
2. **Header Detection**: Scans first 30 lines for actual data header
3. **Header Criteria**:
   - Must contain `"ODS CODE"` AND `"ACCOUNTABLE PROVIDER"`
   - Must have 8+ comma-separated columns
   - Excludes title rows like `"TWO MONTH"`, `"FOUR WEEK"`

**Output**: Extracted CSV with detected encoding and header row index stored in manifest

#### Stage 2: Silver (Data Cleaning & Structuring)
**File**: `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py` (lines 50-104)

**Process**:
1. **Column Name Flattening** (lines 12-48):
   - Multi-level headers converted to snake_case
   - Example: `["Accountable Provider", "ODS Code 1"]` → `accountable_provider`, `ods_code_1`
   - Removes unnamed columns and duplicates

2. **Data Row Filtering** (lines 69-93):
   - Keeps only rows with ODS codes (3-4 character alphanumeric)
   - Filters out metadata rows (keywords: BASIS, DEFINITIONS, FOUR WEEK, PERCENTAGE, TOTAL, WITHIN, AFTER)
   - Validates: Row is not pure digits, contains actual provider codes

3. **Type Coercion** (lines 98-102):
   - Numeric columns: `total`, `within`, `after`, `number` → `float`
   - Percentage columns: `percentage`, `told_within` → `float`

4. **Period & Metric Addition** (lines 95-96):
   - Adds `period` (YYYY-MM) and `metric` (3, 5, or 8) columns

#### Stage 3: Gold (Unified Target Metrics)
**File**: `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py` (lines 106-237)

**Key Function**: `build_target_gold(silver_df)` - Produces unified output with:
- **Columns**: period, metric, metric_label, org_code, org_name, cancer_type, referral_route, within_target, outside_target, pct_within_target

**CRITICAL FILTERING LOGIC** (lines 177-182):

```python
# For metric 5 (31-day): Filter to "ALL STAGES" rows ONLY
if metric_val == 5 and treatment_stage_col and treatment_stage_col in df.columns:
    df = df[df[treatment_stage_col].str.upper().str.strip() == "ALL STAGES"].copy()
```

**Why This Matters**:
- CSV contains three rows per cancer type:
  - `ALL STAGES` (combined first + subsequent treatments)
  - `FIRST TREATMENTS` (only first treatment cases)
  - `SUBSEQUENT TREATMENTS` (re-treatment cases)
- Official NHS England reports use `ALL STAGES`
- Using only `FIRST TREATMENTS` would **undercount patients** and give **incorrect percentages**

**Percentage Calculation** (lines 184-198):
1. If `within_target` and `outside_target` present: `pct = within / (within + outside)`
2. If only `pct_col` and `total_col` present: `within = pct * total`, then `outside = total - within`
3. Recomputes percentage after any aggregation

**Aggregation Step** (lines 225-235):
- Groups by: period, metric, metric_label, org_code, org_name, cancer_type, **referral_route**
- Sums numerators and denominators across rows
- **Recomputes percentage**: `pct_within_target = SUM(within) / SUM(within + outside)`

---

## 2. DATABASE SCHEMA & AGGREGATION

### 2.1 Core Tables

#### `cancer_target_metrics` Table
**File**: `database/migrations/client_specific/002_performance_data_init.sql` (lines 98-110)

```sql
CREATE TABLE performance_data.cancer_target_metrics (
  period VARCHAR NOT NULL,
  metric BIGINT NOT NULL,              -- 3, 5, or 8
  metric_label VARCHAR,
  org_code VARCHAR NOT NULL,
  org_name VARCHAR,
  cancer_type VARCHAR NOT NULL,        -- Specific type (e.g., "Breast", "Lung")
  referral_route VARCHAR NOT NULL,     -- "ALL ROUTES", "URGENT SUSPECTED CANCER", etc.
  within_target NUMERIC,               -- Patient count meeting standard
  outside_target NUMERIC,              -- Patient count NOT meeting standard
  pct_within_target DOUBLE PRECISION,  -- Percentage (0.0-1.0)
  PRIMARY KEY (period, metric, org_code, cancer_type, referral_route)
);
```

**Data Stored**: Disaggregated by cancer type AND referral route

#### Other Key Tables
- `rtt_metrics_gold`: RTT waiting times (by rtt_part_type)
- `oversight_metrics_raw`: Oversight framework raw metrics
- `oversight_league_table_raw`: Oversight league table scores
- `dim_organisations`: Trust metadata (region, type, subtype)

---

### 2.2 View Hierarchy: metric_values_base → insight_metrics_long

#### Level 1: metric_values_base View
**Purpose**: Unified long-form view with source data + preliminary roll-ups
**File**: `database/migrations/client_specific/005_add_cancer_trust_aggregates.sql` (lines 7-348)

**Cancer Processing in metric_values_base** (lines 92-224):

1. **Source Rows** (lines 141-144):
   - `cancer_28`, `cancer_31`, `cancer_62` CTEs select directly from `cancer_target_metrics`
   - Filter: `WHERE referral_route IS NOT NULL` (keeps disaggregated rows only)

2. **Trust-Level Aggregates** (lines 175-224):
   - NEW: `cancer_trust_aggregate` CTE creates aggregates where `cancer_type IS NULL`
   - Purpose: Summarize across all cancer types per trust
   - **Logic for metric 5 (31-day)**:
     ```sql
     -- For 31-day and 62-day: sum only ALL ROUTES rows
     SELECT c.period, c.metric, c.org_code, c.referral_route = 'ALL ROUTES',
            c.cancer_type = NULL,
            SUM(c.within_target) / SUM(c.within_target + c.outside_target) AS pct
     FROM cancer_target_metrics c
     WHERE c.metric IN (5, 8)
       AND c.referral_route = 'ALL ROUTES'
     GROUP BY c.period, c.metric, c.org_code
     ```

3. **Why Filter to ALL ROUTES Only**:
   - Disaggregated rows already sum specific routes (USC, Screening, etc.)
   - Including all routes would **double-count** patients
   - `ALL ROUTES` in database already represents combined disaggregation

**Final Union** (lines 333-345):
- Combines: source cancer rows + cancer_rollup + **cancer_trust_aggregate** + gap metrics

#### Level 2: insight_metrics_long Materialized View
**Purpose**: Add percentile rankings and benchmarking
**File**: `database/migrations/client_specific/002_performance_data_init.sql` (lines 498-549)

**Percentile Calculation** (lines 502-517):
```sql
ranked AS (
  SELECT b.*,
    percent_rank() OVER (
      PARTITION BY b.metric_id, b.period, b.disagg_key
      ORDER BY CASE WHEN b.higher_is_better THEN b.value ELSE -b.value END
    ) AS percentile_overall,
    -- trust_type cohort
    percent_rank() OVER (
      PARTITION BY b.metric_id, b.period, b.disagg_key, b.trust_type
      ...
    ) AS percentile_trust_type,
    -- trust_subtype cohort
    percent_rank() OVER (
      PARTITION BY b.metric_id, b.period, b.disagg_key, b.trust_type, b.trust_subtype
      ...
    ) AS percentile_trust_subtype
)
```

**Key Insight**: 
- Percentiles calculated within `disagg_key` (referral_route | cancer_type | rtt_part_type | entity_level)
- This means different disaggregation combinations get ranked separately
- Trust-level aggregate (cancer_type IS NULL) gets its own percentile window

---

## 3. MCP TOOL QUERY LOGIC

### 3.1 GetComprehensiveTrustPerformance Tool
**File**: `apps/mcp/src/mcp_server/tools/nhs_analytics/tools.py` (lines 589-1255)

#### Query Entry Point
**File**: `apps/mcp/src/mcp_server/tools/nhs_analytics/queries.py` (lines 488-843)

**Function**: `get_comprehensive_performance(engine, org_code, period=None, domains=['rtt','cancer','oversight'], ...)`

#### Cancer-Specific Query Logic (lines 568-800)

1. **Period Handling**:
   - If `period=None` (default): Calls `get_latest_periods_by_domain(engine, domains)`
   - Selects `MAX(period)` per domain from `insight_metrics_long`
   - Different domains can have different periods (RTT/Cancer monthly, Oversight quarterly)

2. **DISTINCT ON Logic** (lines 591-610):
   ```sql
   -- Default: deduplicate to one row per metric_id
   DISTINCT ON (metric_id)
   ORDER BY
     metric_id,
     cancer_type NULLS FIRST,           -- Prioritize NULL (trust-level aggregate)
     CASE WHEN referral_route = 'ALL ROUTES' THEN 0 ... END,  -- Prioritize ALL ROUTES
     ...
   ```

3. **Where Clause Filtering** (lines 785-795):
   ```python
   if domain == 'cancer' and not include_cancer_breakdown:
       # Exclude route/type breakdowns, keep trust-level aggregates only
       where_clauses.append("tm.cancer_type IS NULL")
       where_clauses.append("(tm.referral_route = 'ALL ROUTES' OR tm.referral_route IS NULL)")
   ```

**Result**: Selects **only trust-level aggregates** (cancer_type IS NULL, ALL ROUTES)

#### Tool Output Processing (lines 925-1022)

1. **Filtering** (lines 971-976):
   ```python
   overall_cancer_metrics = [
       m for m in metrics_by_domain['cancer']
       if m.get('cancer_type') is None and m.get('referral_route') == 'ALL ROUTES'
   ]
   ```

2. **Deduplication** (lines 978-990):
   - Defensive deduplication by metric_id
   - Logs if duplicates found

3. **Display** (lines 997-1007):
   - Shows: Standard, Value, Target, Met status, National %, Numerator, Denominator
   - Numerator/Denominator are aggregated patient counts

---

## 4. POTENTIAL SOURCES OF DISCREPANCIES

### Critical Point: Different Aggregation Levels

#### Scenario: 88% vs 90.7% for Cancer 31-Day

**Possible Explanation 1: Disaggregated vs Aggregated**
```
88.0%  = Single cancer type + single referral route (low sample size ~100-200 patients)
90.7%  = Trust-level aggregate across ALL cancer types (large sample size ~2000+ patients)
```

**Database Evidence**:
- `cancer_target_metrics` table stores: (period, metric, org_code, cancer_type, referral_route)
- One row per cancer type × route × org
- Trust-level aggregate row has: cancer_type IS NULL, referral_route = 'ALL ROUTES'

**Tool Logic Evidence**:
- Tool queries: `WHERE cancer_type IS NULL AND referral_route = 'ALL ROUTES'`
- Returns trust-level aggregates only
- This is 90.7% (larger population)

**Where 88% Could Come From**:
- Direct SQL query to `cancer_target_metrics` without the aggregation
- Querying specific cancer_type (e.g., Breast Cancer with 150 patients)
- Different referral route filtering
- Old code before `cancer_trust_aggregate` CTE was added

#### Scenario: Different Filtering Rules

**Period Filtering**:
- Cancer data loads monthly (YYYY-MM)
- Different data points might use different latest periods
- Tool auto-selects `MAX(period)` - could differ if database contains mixed periods

**Treatment Stage Filtering** (CRITICAL for Metric 5):
- Source CSV contains: ALL STAGES, FIRST TREATMENTS, SUBSEQUENT TREATMENTS
- Transforms.py filters to `ALL STAGES` (lines 177-182)
- **If old code used FIRST TREATMENTS**: Would give ~50-60% lower patient counts, different percentage
- **If ALL STAGES not properly filtered**: Could mix treatment categories

**Referral Route Filtering**:
- Could aggregate wrong routes
- USC-only vs ALL ROUTES would give different results

### Other Potential Sources

1. **Sample Size Exclusion** (min_denominator):
   - Metric catalogue specifies `min_denominator = 20`
   - `insight_metrics_long` filters: `WHERE valid_sample = true`
   - If denominator < 20: marked invalid, excluded from percentile calculations
   - But still present in output - could show as "valid" in one view, invalid in another

2. **Data Quality Flags**:
   - `valid_sample` = (denominator >= min_denominator) OR (denominator IS NULL)
   - Rows with small denominators get `valid_sample = FALSE`
   - Tool filters: `WHERE valid_sample = true` in percentile calculations
   - But base metric value still displayed

3. **Percentage Rounding**:
   - Pipeline: `pct_within_target` = numerator / denominator (0.0-1.0 float)
   - Tool formatting: `format_value_with_unit()` applies rounding
   - Different rounding logic could give 0.88 vs 0.907

4. **Aggregation Time**:
   - Percentages recalculated at multiple points:
     - In transforms.py: `build_target_gold()`
     - In database view: `cancer_trust_aggregate` CTE
     - In tool: formatters
   - Floating point precision errors could accumulate

5. **Database Stale Data**:
   - Materialized view `insight_metrics_long` requires manual refresh
   - If not refreshed after data load: could serve old percentages
   - Migration 005 ends with: `REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;`

---

## 5. DATA FLOW DIAGRAM

```
NHS England Website (CSV)
    ↓
cancer/scraper.py
    └─ Discovers metric URLs (period, metric 3|5|8, is_final)
    ↓
cancer/extractor.py
    └─ Detects encoding, finds header row
    ↓
transforms.py::load_bronze()
    └─ Loads raw CSV with multi-level headers
    ↓
transforms.py::build_silver()
    └─ Cleans column names, filters ODS codes, converts types
    ↓
transforms.py::build_target_gold()
    ├─ Filters metric 5 to "ALL STAGES" ONLY ← CRITICAL
    ├─ Derives within/outside/pct from available columns
    ├─ Aggregates by: period, metric, org_code, cancer_type, referral_route
    └─ Recomputes: pct = SUM(within) / SUM(within + outside)
    ↓
cancer_target_metrics Table
    └─ Stores disaggregated by (period, metric, org_code, cancer_type, referral_route)
    ↓
metric_values_base View
    ├─ Unions cancer_union (source rows)
    ├─ Adds cancer_rollup (derived ALL ROUTES per cancer_type)
    └─ Adds cancer_trust_aggregate (new: aggregates across cancer_types)
         └─ For metric 5: SUM(within) / SUM(within + outside) where referral_route = 'ALL ROUTES'
    ↓
insight_metrics_long Materialized View
    └─ Calculates percentile_overall, percentile_trust_type, percentile_trust_subtype
    └─ Partitions by: metric_id, period, disagg_key
    └─ disagg_key = referral_route | cancer_type | rtt_part_type | entity_level
    ↓
GetComprehensiveTrustPerformance Tool
    ├─ Queries: SELECT * WHERE cancer_type IS NULL AND referral_route = 'ALL ROUTES'
    └─ Returns: Trust-level aggregate metrics with percentiles
```

---

## 6. KEY FILES & LOCATIONS

### Pipeline Code
| File | Purpose |
|------|---------|
| `pipelines/outcomes_data/outcomes_data/data_sources/cancer/scraper.py` | Discovers metric CSVs from NHS site |
| `pipelines/outcomes_data/outcomes_data/data_sources/cancer/extractor.py` | Detects encoding and header row |
| `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py` | Bronze→Silver→Gold transformation (FILTERING & AGGREGATION) |
| `pipelines/outcomes_data/outcomes_data/data_sources/cancer/pipeline.py` | Orchestration: discover → extract → transform → load |

### Database Schema
| File | Content |
|------|---------|
| `database/migrations/client_specific/002_performance_data_init.sql` | Core tables, metric_values_base, insight_metrics_long |
| `database/migrations/client_specific/005_add_cancer_trust_aggregates.sql` | cancer_trust_aggregate CTE (replaces metric_values_base) |

### MCP Tools
| File | Purpose |
|------|---------|
| `apps/mcp/src/mcp_server/tools/nhs_analytics/queries.py` | SQL query builders, get_comprehensive_performance() |
| `apps/mcp/src/mcp_server/tools/nhs_analytics/tools.py` | GetComprehensiveTrustPerformance tool (lines 589-1255) |
| `apps/mcp/src/mcp_server/tools/nhs_analytics/formatters.py` | Markdown formatting, rounding |

---

## 7. DEBUGGING DISCREPANCIES: Step-by-Step

### If Tool Shows 90.7% But Should Show 88%:

1. **Check Source Data**:
   ```bash
   psql -c "SELECT * FROM performance_data.cancer_target_metrics 
            WHERE org_code = 'YOUR_CODE' AND metric = 5 
            ORDER BY cancer_type, referral_route LIMIT 20"
   ```
   Look for: Rows with different cancer_types showing 88%, or specific referral route showing 88%

2. **Check Aggregation**:
   ```bash
   psql -c "SELECT cancer_type, referral_route, within_target, outside_target, 
                   pct_within_target FROM performance_data.cancer_target_metrics 
            WHERE org_code = 'YOUR_CODE' AND metric = 5 AND period = '2025-08'
            ORDER BY cancer_type, referral_route"
   ```
   Sum manually: Is 90.7% = SUM(within) / SUM(within+outside) across all rows?

3. **Check View**:
   ```bash
   psql -c "SELECT * FROM performance_data.metric_values_base 
            WHERE org_code = 'YOUR_CODE' AND metric_id = 'cancer_31d_pct_within_target'"
   ```
   Should show both disaggregated AND aggregated (cancer_type IS NULL) rows

4. **Check Materialized View**:
   ```bash
   psql -c "SELECT * FROM performance_data.insight_metrics_long 
            WHERE org_code = 'YOUR_CODE' AND metric_id = 'cancer_31d_pct_within_target' 
            AND cancer_type IS NULL"
   ```
   Should show 90.7% with percentile_overall calculated

5. **Check Tool Query**:
   Enable query logging, capture SQL:
   ```python
   # Add to queries.py line 816-820
   logger.info(f"Query being executed:\n{query}")
   logger.info(f"Query params: {query_params}")
   ```

6. **Check Formatting**:
   Look at `formatters.py::format_value_with_unit()` - how is 90.7 being rounded/displayed?

---

## 8. SUMMARY: WHERE DISCREPANCIES OCCUR

| Stage | Risk Level | Issue | Example |
|-------|-----------|-------|---------|
| **Source** | MEDIUM | Different CSV files for same period | Provisional vs final versions |
| **Bronze** | LOW | Encoding detection failure | Rare with chardet |
| **Silver** | HIGH | ODS code filtering logic | Could exclude valid rows |
| **Gold (Transforms)** | **CRITICAL** | Treatment stage filtering (metric 5) | ALL STAGES vs FIRST TREATMENTS ↔ 50-60% difference |
| **Gold (Aggregation)** | MEDIUM | Numerator/denominator summation | Floating point precision |
| **Database** | MEDIUM | Percentage recalculation at aggregation | Different rounding at each step |
| **Views** | MEDIUM | Percentile partition keys | Wrong disagg_key could use wrong cohort |
| **Tool Query** | LOW | DISTINCT ON and WHERE filtering | Already tested and documented |
| **Tool Output** | LOW | Rounding in formatters | Usually minor (0.1-0.2%) |

**Most Likely Cause**: Treatment stage filtering or cancer_type/referral_route aggregation level difference.

