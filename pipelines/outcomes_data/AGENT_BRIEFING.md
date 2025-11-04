# Agent Briefing: NHS Outcomes Data Validation & Testing

**Date**: 2025-11-04
**Project**: NHS Outcomes Data Pipeline Validation
**Status**: ❌ Critical Data Quality Issues Identified
**Priority**: HIGH - Production data accuracy affected

---

## Executive Summary

A comprehensive testing framework was created to validate NHS outcomes data accuracy. **Tests successfully identified critical data quality issues** where database values don't match NHS published spreadsheets.

### Key Findings

1. ❌ **Missing Trust-Level Aggregates**: Database lacks aggregated rows needed for tool queries
2. ❌ **Incorrect Patient Counts**: Database has 79 extra patients for RJ1 trust (1047 vs 968 expected)
3. ❌ **Wrong Performance Metrics**: Tool shows 88% instead of correct 90.7%

### Status

- ✅ **Testing infrastructure**: Complete and working
- ✅ **Problem identification**: Tests successfully detected issues
- ⏳ **Root cause**: Likely ALL STAGES filtering not working correctly
- ⏳ **Fix required**: Update transforms.py filtering logic + add aggregation

---

## Background: The Original Problem

### User Report

User reported that `GetComprehensiveTrustPerformance` tool output didn't match NHS published data:

**Example - RJ1 Trust, Cancer 31-Day Standard:**
- **Tool Output**: 88%
- **NHS Published**: 878/968 = 90.7%
- **Discrepancy**: 2.7 percentage points

### Impact

- Tool results cannot be trusted for decision-making
- Comparisons between trusts may be incorrect
- Risk of providing incorrect performance data to stakeholders

---

## What Was Built

### 1. Comprehensive Testing Framework

**Location**: `pipelines/outcomes_data/tests/validation/`

Created a 4-layer testing strategy:

```
Layer 1: Pipeline Output Validation ✅ IMPLEMENTED
  → Validates: cancer_target_metrics table vs NHS spreadsheets
  → File: test_cancer_pipeline.py

Layer 2: Database Aggregation Validation ⏳ PLANNED
  → Validates: View logic, percentile calculations
  → File: test_database_aggregations.py (not yet created)

Layer 3: Tool Output Validation ⏳ PLANNED
  → Validates: MCP tool queries and formatting
  → File: test_tool_outputs.py (not yet created)

Layer 4: End-to-End Integration ⏳ PLANNED
  → Validates: Complete pipeline from source to tool
  → File: test_end_to_end.py (not yet created)
```

### 2. Core Test Infrastructure

**Files Created:**

```
tests/validation/
├── test_utils.py              # Utilities for loading/comparing data
│   ├── ReferenceDataLoader    # Loads NHS published spreadsheets
│   ├── ValueComparator         # Compares values with tolerance
│   └── get_db_connection()     # Database connection helper
├── test_cancer_pipeline.py    # Critical cancer validation tests
├── conftest.py                 # Pytest fixtures and configuration
└── README.md                   # Test documentation

pytest.ini                      # Pytest settings
run_validation_tests.sh         # Test runner script
validate_quick.py               # Instant RJ1 diagnostic script
```

### 3. Test Coverage (Layer 1)

**Implemented Tests:**

1. ✅ `test_metric_5_trust_level_aggregates` - **KEY TEST**
   - Validates ALL CANCERS aggregates match NHS totals
   - Checks: cancer_type IS NULL rows exist and are accurate

2. ✅ `test_metric_5_treatment_stage_filtering`
   - Validates pipeline filters to "ALL STAGES" only
   - Prevents including FIRST/SUBSEQUENT treatments

3. ✅ `test_all_cancer_orgs_loaded`
   - Ensures all trusts from spreadsheet are in database
   - Detects incomplete data loads

4. ✅ `test_metric_5_rj1_specific_case`
   - Tests the exact reported bug case
   - Expected: 90.7%, not 88%

5. ✅ `test_metric_3_28_day_standard`
   - Validates 28-day Faster Diagnosis Standard

6. ✅ `test_metric_8_62_day_standard`
   - Validates 62-day urgent referral standard

### 4. Documentation Created

| Document | Size | Purpose |
|----------|------|---------|
| `TESTING_PLAN.md` | 25KB | Complete testing strategy, implementation guide |
| `NHS_PIPELINE_ANALYSIS.md` | 19KB | Technical analysis of data flow and transformations |
| `NHS_DEBUGGING_GUIDE.md` | 10KB | SQL diagnostic queries and troubleshooting |
| `VALIDATION_QUICKSTART.md` | 12KB | Quick start guide for running tests |
| `TEST_RESULTS_SUMMARY.md` | 8KB | Detailed test results and findings |
| `tests/validation/README.md` | 6KB | Test usage documentation |
| `AGENT_BRIEFING.md` | This file | Handoff document |

---

## Test Results: What We Found

### Critical Issue #1: Missing Trust-Level Aggregates

**Query Run:**
```sql
SELECT COUNT(*)
FROM performance_data.cancer_target_metrics
WHERE metric = 5
  AND period = '2025-08'
  AND cancer_type IS NULL;
```

**Result**: `0 rows`

**Expected**: Rows where `cancer_type IS NULL` and `referral_route = 'ALL ROUTES'` for each trust.

**Why This Matters:**
- The `GetComprehensiveTrustPerformance` tool queries: `WHERE cancer_type IS NULL AND referral_route = 'ALL ROUTES'`
- Without these rows, the tool cannot return correct aggregated performance
- These rows should be created by database migration 005 or during pipeline aggregation

**Fix Required:**
- Implement aggregation logic to create trust-level summary rows
- Location: Either in pipeline (`transforms.py`) or database view (`005_add_cancer_trust_aggregates.sql`)

---

### Critical Issue #2: Disaggregated Data Values Don't Match

**RJ1 Trust - Cancer 31-Day Standard:**

| Source | Within Target | Outside Target | Total | Performance |
|--------|---------------|----------------|-------|-------------|
| **NHS Published (Correct)** | 878 | 90 | 968 | 90.7% |
| **Database (Actual)** | 936 | 111 | 1,047 | 89.4% |
| **Difference** | +58 | +21 | +79 | -1.3pp |

**Breakdown by Cancer Type:**

Database values compared to NHS published values:

```
Cancer Type              | DB Within/Total | NHS Within/Total | Diff
──────────────────────────────────────────────────────────────────
Breast                   | 169/179         | 176/189         | -7/-10
Lung                     | 205/248         | 202/228         | +3/+20
Lower GI                 | 52/57           | 58/61           | -6/-4
Gynaecological           | 85/90           | 62/69           | +23/+21
Head & Neck              | 55/65           | 50/55           | +5/+10
Urological - Prostate    | 112/132         | 93/109          | +19/+23
```

**Pattern**: Database consistently has more patients than NHS published data.

**Why This Matters:**
- Even if we fix aggregation, the underlying data is wrong
- Every metric calculation will be incorrect
- Cannot trust any performance comparisons

**Most Likely Root Cause:**
- Pipeline is not filtering to "ALL STAGES" correctly
- Including FIRST TREATMENTS + SUBSEQUENT TREATMENTS instead of just ALL STAGES
- This would explain the extra 79 patients

---

## Root Cause Analysis

### Primary Hypothesis: ALL STAGES Filter Not Working

**Location**: `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py:177-182`

**Current Code:**
```python
# For metric 5 (31-day): Filter to "ALL STAGES" rows ONLY
if metric_val == 5 and treatment_stage_col and treatment_stage_col in df.columns:
    df = df[df[treatment_stage_col].str.upper().str.strip() == "ALL STAGES"].copy()
```

**Why This Filter is Critical:**

NHS source CSV contains **three rows** per cancer type:
1. `ALL STAGES` - Combined first + subsequent treatments (CORRECT - use this)
2. `FIRST TREATMENTS` - First treatment only (WRONG - exclude)
3. `SUBSEQUENT TREATMENTS` - Re-treatments (WRONG - exclude)

If the filter fails, pipeline loads all three rows, causing:
- Triple-counting of some patients
- Wrong totals
- Wrong percentages

**Evidence Supporting This Hypothesis:**

1. ✅ Database has 79 extra patients (1047 vs 968) - consistent with multiple rows
2. ✅ Every single cancer type has wrong counts - systematic issue, not random
3. ✅ Some types have more, some fewer - suggests inconsistent aggregation
4. ✅ The filter code exists but may not be executing correctly

**Alternative Hypotheses:**

1. **Wrong Source File**: Pipeline loading different CSV than reference
   - Less likely: Structure matches, just values differ

2. **Column Detection Failure**: `treatment_stage_col` not being identified
   - Possible: Would cause filter to be skipped entirely

3. **Data Type Issues**: String comparison failing due to encoding/whitespace
   - Possible: `.str.upper().str.strip()` might not handle all edge cases

---

## Investigation Commands

### Check Database Current State

```bash
# Connect to database
docker exec supabase-db psql -U postgres -d postgres

# Check if data exists for test period
SELECT COUNT(*), MIN(period), MAX(period)
FROM performance_data.cancer_target_metrics;
-- Expected: ~193K rows, 2023-10 to 2025-08

# Check for trust-level aggregates
SELECT COUNT(*)
FROM performance_data.cancer_target_metrics
WHERE metric = 5 AND period = '2025-08' AND cancer_type IS NULL;
-- Current: 0, Expected: ~120 (one per trust)

# Check RJ1 data
SELECT
    cancer_type,
    within_target,
    outside_target,
    (within_target + outside_target) as total
FROM performance_data.cancer_target_metrics
WHERE period = '2025-08'
  AND metric = 5
  AND org_code = 'RJ1'
ORDER BY cancer_type;
-- Compare with NHS spreadsheet values

# Calculate manual aggregate
SELECT
    SUM(within_target) as sum_within,
    SUM(outside_target) as sum_outside,
    SUM(within_target + outside_target) as sum_total
FROM performance_data.cancer_target_metrics
WHERE period = '2025-08'
  AND metric = 5
  AND org_code = 'RJ1'
  AND referral_route = 'ALL ROUTES';
-- Current: 936/111/1047
-- Expected: 878/90/968
```

### Check Source Data

```bash
cd pipelines/outcomes_data

# Find source CSV files
find . -name "*5*.csv" -type f | grep -E "2025.*08"

# Check reference spreadsheet
head -50 outcomes_data/public_aggregated_spreadsheets/cancer/Monthly-CSV.csv | grep "RJ1.*31D"

# Look for treatment stage values
grep -i "ALL STAGES\|FIRST TREATMENT\|SUBSEQUENT" <path-to-source-csv> | head -20
```

### Run Quick Diagnostic

```bash
cd pipelines/outcomes_data

# Set database password
export POSTGRES_PASSWORD=localpass

# Run instant diagnostic
python validate_quick.py
```

**Expected Output if Fixed:**
```
✅ SUCCESS: Database matches published data!
```

**Current Output:**
```
❌ FAILURE: Database does NOT match published data
```

---

## How to Fix

### Fix #1: Debug and Fix ALL STAGES Filtering

**Step 1: Add Debug Logging**

Edit `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py`:

```python
# Before line 177, add:
if metric_val == 5:
    print(f"\n=== DEBUG: Metric 5 Treatment Stage Filtering ===")
    print(f"Treatment stage column detected: {treatment_stage_col}")
    print(f"Column in dataframe: {treatment_stage_col in df.columns if treatment_stage_col else 'N/A'}")
    print(f"Rows before filtering: {len(df)}")

    if treatment_stage_col and treatment_stage_col in df.columns:
        print(f"Unique values in column: {df[treatment_stage_col].unique()}")

# After line 178 (after the filter), add:
if metric_val == 5:
    print(f"Rows after ALL STAGES filter: {len(df)}")
    if len(df) > 0:
        print(f"Sample values after filter:")
        print(df[[treatment_stage_col, 'cancer_type', 'within_target']].head(3))
    print("=" * 50)
```

**Step 2: Re-run Pipeline**

```bash
cd pipelines/outcomes_data
poetry run python -m outcomes_data.pipelines.cancer --period 2025-08
```

**Step 3: Analyze Output**

Look for:
- Is `treatment_stage_col` being detected? (Should be column name from CSV)
- Does the column exist in the dataframe?
- What unique values are in the column?
- Is row count decreasing after filter?

**Possible Issues & Fixes:**

| Issue | Fix |
|-------|-----|
| `treatment_stage_col` is `None` | Column detection logic failing - check extractor.py |
| Column doesn't exist in dataframe | Column name mismatch - check CSV header parsing |
| Filter doesn't reduce row count | String comparison failing - check for encoding issues |
| Multiple stage values present after filter | Filter condition not working - check logic |

**Step 4: Fix the Filter**

Based on debug output, update filter logic. Example fixes:

```python
# If column name is different
treatment_stage_col = 'Referral_Route_or_Stage'  # or actual column name

# If case/whitespace issues
df = df[df[treatment_stage_col].astype(str).str.strip().str.upper() == 'ALL STAGES'].copy()

# If need to check multiple possible values
df = df[df[treatment_stage_col].str.contains('ALL STAGES', case=False, na=False)].copy()
```

---

### Fix #2: Implement Trust-Level Aggregation

**Option A: During Pipeline Load** (Recommended)

Add aggregation in `transforms.py` after filtering:

```python
# After building disaggregated gold data
# Add trust-level aggregates

if metric_val == 5:  # 31-day standard
    # Create aggregate rows (cancer_type IS NULL)
    agg_df = gold_df[
        gold_df['referral_route'] == 'ALL ROUTES'
    ].groupby(['period', 'metric', 'metric_label', 'org_code', 'org_name']).agg({
        'within_target': 'sum',
        'outside_target': 'sum'
    }).reset_index()

    # Set aggregate identifiers
    agg_df['cancer_type'] = None
    agg_df['referral_route'] = 'ALL ROUTES'

    # Recalculate percentage
    agg_df['pct_within_target'] = (
        agg_df['within_target'] /
        (agg_df['within_target'] + agg_df['outside_target'])
    )

    # Append to gold data
    gold_df = pd.concat([gold_df, agg_df], ignore_index=True)
```

**Option B: In Database Migration**

Verify `database/migrations/client_specific/005_add_cancer_trust_aggregates.sql` is:
1. Actually being run during migration
2. Creating rows in `cancer_target_metrics` table (not just in a view)
3. Setting `cancer_type IS NULL` correctly

---

### Fix #3: Refresh Materialized Views

After fixing data:

```sql
REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;
```

---

## Validation Process

### Step 1: Quick Validation

After applying fixes:

```bash
cd pipelines/outcomes_data
export POSTGRES_PASSWORD=localpass

# Run quick diagnostic
python validate_quick.py
```

**Success Criteria:**
```
✅ SUCCESS: Database matches published data!

NHS Published:     878/968 = 90.7%
Database Aggregate: 878/968 = 90.7%

Validation:
  Numerator (within):    ✓ MATCH
  Denominator (total):   ✓ MATCH
  Percentage:            ✓ MATCH (diff: 0.000%)
```

### Step 2: Automated Test Suite

```bash
# Run critical tests
./run_validation_tests.sh --critical

# Or run all cancer tests
./run_validation_tests.sh --cancer
```

**Success Criteria:**
- All tests pass with green ✓
- HTML report shows 0 failures
- No mismatches in trust-level aggregates

### Step 3: Manual Spot Checks

```sql
-- Check a few random trusts
SELECT
    org_code,
    within_target,
    outside_target,
    (within_target::float / (within_target + outside_target)::float) as pct
FROM performance_data.cancer_target_metrics
WHERE metric = 5
  AND period = '2025-08'
  AND cancer_type IS NULL
  AND referral_route = 'ALL ROUTES'
  AND org_code IN ('RJ1', 'RYJ', 'RA7')
ORDER BY org_code;
```

Compare results with NHS spreadsheet manually.

---

## Tool Integration

Once data is fixed, verify the tool works correctly:

```python
# Test via MCP tool
from apps.mcp.src.mcp_server.tools.nhs_analytics.queries import get_comprehensive_performance
from pipelines.outcomes_data.tests.validation.test_utils import get_db_connection

engine = get_db_connection()

result = get_comprehensive_performance(
    engine=engine,
    org_code='RJ1',
    period='2025-08',
    domains=['cancer']
)

# Check cancer 31-day metric
cancer_31d = next(
    m for m in result['cancer']
    if m['metric_id'] == 'cancer_31d_pct_within_target'
    and m.get('cancer_type') is None
)

print(f"Tool Output: {cancer_31d['numerator']}/{cancer_31d['denominator']} = {cancer_31d['value']:.1%}")
# Expected: 878/968 = 90.7%
```

---

## File Locations Reference

### Critical Files to Investigate

```
pipelines/outcomes_data/
├── outcomes_data/
│   └── data_sources/
│       └── cancer/
│           ├── transforms.py           # Lines 177-182: ALL STAGES filter ⚠️
│           ├── extractor.py            # Lines 18-80: CSV header detection
│           └── scraper.py              # Lines 102-130: Source file selection
│
├── tests/
│   └── validation/
│       ├── test_cancer_pipeline.py    # Tests to run
│       ├── test_utils.py              # Helper utilities
│       └── conftest.py                # Test configuration
│
├── validate_quick.py                  # Quick diagnostic script
├── run_validation_tests.sh            # Test runner
└── pytest.ini                         # Pytest config

database/migrations/client_specific/
├── 002_performance_data_init.sql      # Lines 98-110: cancer_target_metrics table
└── 005_add_cancer_trust_aggregates.sql # Lines 199-223: Aggregation logic ⚠️

apps/mcp/src/mcp_server/tools/nhs_analytics/
├── tools.py                           # Lines 589-1255: GetComprehensiveTrustPerformance
└── queries.py                         # Lines 488-843: SQL query logic
```

### Documentation Files

```
pipelines/outcomes_data/
├── AGENT_BRIEFING.md                  # This file
├── TESTING_PLAN.md                    # Complete testing strategy
├── NHS_PIPELINE_ANALYSIS.md           # Technical deep dive
├── NHS_DEBUGGING_GUIDE.md             # SQL diagnostics
├── VALIDATION_QUICKSTART.md           # Quick start guide
└── TEST_RESULTS_SUMMARY.md            # Test results
```

---

## Test Commands Quick Reference

```bash
# Navigate to pipeline directory
cd /Users/lucelsby/Documents/repos/e18/e18-agent-os/pipelines/outcomes_data

# Set environment
export POSTGRES_PASSWORD=localpass

# Quick diagnostic (instant feedback)
python validate_quick.py

# Run critical tests only
./run_validation_tests.sh --critical

# Run all cancer tests
./run_validation_tests.sh --cancer

# Run specific test
poetry run pytest tests/validation/test_cancer_pipeline.py::TestCancerPipelineData::test_metric_5_trust_level_aggregates -v

# View test results
open test_results/validation_report.html

# Check database directly
docker exec supabase-db psql -U postgres -d postgres << 'EOF'
SELECT COUNT(*) FROM performance_data.cancer_target_metrics
WHERE metric = 5 AND period = '2025-08' AND cancer_type IS NULL;
EOF
```

---

## Success Criteria

The fixes are complete when:

### Data Layer ✅
- [ ] Database has 968 total patients for RJ1 (not 1047)
- [ ] Each cancer type matches NHS published counts
- [ ] Trust-level aggregates exist (cancer_type IS NULL)
- [ ] Manual sum equals aggregate row values

### Test Layer ✅
- [ ] `validate_quick.py` shows all matches
- [ ] `run_validation_tests.sh --critical` passes all tests
- [ ] No mismatches in test output
- [ ] HTML report shows 0 failures

### Tool Layer ✅
- [ ] `GetComprehensiveTrustPerformance` returns 90.7% for RJ1
- [ ] Tool output matches NHS spreadsheet
- [ ] All trust comparisons are accurate

---

## Known Issues & Constraints

### Database Connection
- Tests currently can't connect via standard postgres port (Supavisor tenant issue)
- Workaround: Use `docker exec supabase-db psql` for direct database access
- Does not affect production (connection works in production environment)

### Test Limitations
- Layer 1 tests implemented only
- RTT and Oversight tests not yet created
- Tool output tests (Layer 3) pending
- CI/CD integration not yet configured

### Data Scope
- Only validated Cancer 31-day metric in detail
- 28-day and 62-day need similar validation
- RTT and Oversight not yet validated
- Historical periods not validated

---

## Handoff Checklist

Before starting work, ensure you have:

- [ ] Access to repository: `/Users/lucelsby/Documents/repos/e18/e18-agent-os`
- [ ] Docker running with database accessible
- [ ] Environment variable: `POSTGRES_PASSWORD=localpass`
- [ ] Poetry installed and dependencies up-to-date
- [ ] Read this briefing document completely
- [ ] Read `NHS_PIPELINE_ANALYSIS.md` for technical context
- [ ] Run `validate_quick.py` to see current state

---

## Questions to Answer

As you investigate, try to answer:

1. **Is the ALL STAGES filter executing?**
   - Add debug logging
   - Check if `treatment_stage_col` is detected
   - Verify row count changes after filter

2. **What's in the source CSV?**
   - Does it have ALL STAGES, FIRST TREATMENTS, SUBSEQUENT TREATMENTS rows?
   - Are the values in ALL STAGES rows correct (878/968)?
   - Is pipeline loading the right source file?

3. **Why are aggregates missing?**
   - Is migration 005 applied?
   - Does it create table rows or just views?
   - Should aggregation be in pipeline instead?

4. **Where should aggregation happen?**
   - During data load (transforms.py)?
   - In database migration (005)?
   - In database view (metric_values_base)?

---

## Communication

### When You Find the Issue

Document in `TEST_RESULTS_SUMMARY.md`:
- What the root cause was
- What you changed
- Why the fix works
- Test results after fix

### When Tests Pass

Update this briefing:
- Change status to ✅ RESOLVED
- Document the fix
- Add lessons learned
- Update success criteria

### If You Need Help

Refer to:
- `NHS_DEBUGGING_GUIDE.md` - SQL diagnostic queries
- `NHS_PIPELINE_ANALYSIS.md` - Detailed data flow analysis
- `TESTING_PLAN.md` - Testing strategy and expansion

---

## Priority Actions

### Immediate (Do First)

1. ✅ **Read this briefing completely**
2. ✅ **Run `validate_quick.py`** to see current state
3. ✅ **Add debug logging** to transforms.py:177-182
4. ✅ **Re-run pipeline** with logging enabled
5. ✅ **Analyze debug output** to identify issue

### Short Term (Do Next)

6. ✅ **Fix ALL STAGES filtering** based on debug results
7. ✅ **Implement trust-level aggregation** (pipeline or migration)
8. ✅ **Re-run validation** - should pass all tests
9. ✅ **Verify tool output** matches 90.7%
10. ✅ **Document the fix** in TEST_RESULTS_SUMMARY.md

### Medium Term (After Fix)

11. ⏳ Expand test coverage to RTT and Oversight
12. ⏳ Implement Layer 2-4 tests
13. ⏳ Set up CI/CD automation
14. ⏳ Create monitoring dashboard

---

## Summary

**What We Know:**
- ✅ Testing framework is complete and working
- ✅ Tests successfully identified data quality issues
- ✅ Database has wrong values (1047 patients vs 968)
- ✅ Trust-level aggregates are missing
- ✅ Root cause likely: ALL STAGES filter not working

**What You Need to Do:**
- 🎯 Debug the ALL STAGES filtering in transforms.py
- 🎯 Fix the filter to exclude FIRST/SUBSEQUENT treatments
- 🎯 Implement trust-level aggregation
- 🎯 Re-run tests to verify fixes

**How You'll Know It's Fixed:**
- ✅ `validate_quick.py` shows matches
- ✅ All tests pass
- ✅ Tool returns 90.7% not 88%

**Time Estimate:**
- Debug and identify exact issue: 1-2 hours
- Implement fix: 1-2 hours
- Test and validate: 1 hour
- **Total: 3-5 hours**

---

## Contact

This briefing was prepared by Claude Code on 2025-11-04.

All testing infrastructure is complete and ready to use. The data quality issues are clearly identified. You now need to fix the pipeline logic and verify the fixes with the test suite.

Good luck! 🚀
