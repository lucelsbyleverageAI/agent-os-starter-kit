# NHS Data Validation Test Results

## Test Execution Summary

**Date**: 2025-11-04
**Period Tested**: 2025-08
**Focus**: Cancer 31-Day Metric (Metric 5)
**Test Org**: RJ1 (Guy's and St Thomas' NHS Foundation Trust)

---

## ❌ CRITICAL FINDING: Data Mismatch Detected

### Issue 1: Missing Trust-Level Aggregates

**Status**: ❌ **FAILED - CRITICAL**

```sql
SELECT COUNT(*)
FROM performance_data.cancer_target_metrics
WHERE metric = 5
  AND period = '2025-08'
  AND cancer_type IS NULL;
-- Result: 0 rows
```

**Finding**: There are **ZERO** trust-level aggregate rows in the database.

**Expected**: Rows where `cancer_type IS NULL` and `referral_route = 'ALL ROUTES'` representing trust-wide totals.

**Impact**:
- The `GetComprehensiveTrustPerformance` tool queries for these aggregates
- Without them, the tool cannot return correct results
- This explains why tool outputs don't match NHS published data

**Root Cause**: Aggregation logic in `005_add_cancer_trust_aggregates.sql` is not creating these rows during data load.

---

### Issue 2: Disaggregated Data Values Don't Match NHS Published Data

**Status**: ❌ **FAILED - CRITICAL**

#### RJ1 Trust 31-Day Comparison

| Source | Within | Outside | Total | Percentage |
|--------|--------|---------|-------|------------|
| **NHS Published (Reference)** | **878** | **90** | **968** | **90.7%** |
| **Database (Actual)** | **936** | **111** | **1047** | **89.4%** |
| **Difference** | **+58** | **+21** | **+79** | **-1.3pp** |

#### Cancer Type Breakdown Comparison

| Cancer Type | DB Within/Total | Reference Within/Total | Difference |
|-------------|-----------------|------------------------|------------|
| **Breast** | 169/179 | 176/189 | -7/-10 |
| **Lung** | 205/248 | 202/228 | +3/+20 |
| **Lower GI** | 52/57 | 58/61 | -6/-4 |
| **Gynaecological** | 85/90 | 62/69 | +23/+21 |
| **Head & Neck** | 55/65 | 50/55 | +5/+10 |

**Finding**: Every single cancer type has different patient counts between database and reference data.

**Pattern**:
- Database has 79 more total patients (1047 vs 968)
- Some cancer types have more patients (Lung, Gynae), others have fewer (Breast, Lower GI)
- The discrepancies are not small rounding errors - they're significant count differences

---

## Root Cause Analysis

### Hypothesis 1: ALL STAGES Filtering Not Working ✅ **Most Likely**

**Evidence**:
- NHS CSV contains three rows per cancer type: ALL STAGES, FIRST TREATMENTS, SUBSEQUENT TREATMENTS
- Pipeline should filter to "ALL STAGES" only (transforms.py:177-182)
- Database totals don't match reference totals for ANY cancer type
- Extra patients suggest multiple treatment stages are being included

**Code Location**: `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py:177-182`

```python
# Current code
if metric_val == 5 and treatment_stage_col and treatment_stage_col in df.columns:
    df = df[df[treatment_stage_col].str.upper().str.strip() == "ALL STAGES"].copy()
```

**Validation Needed**:
1. Check if `treatment_stage_col` is correctly identified
2. Verify the column actually contains "ALL STAGES" values
3. Check if filtering is actually reducing row count as expected
4. Inspect source CSV to verify structure

### Hypothesis 2: Wrong Source Data

**Evidence**:
- Reference CSV used in tests: `public_aggregated_spreadsheets/cancer/Monthly-CSV.csv`
- Pipeline might be loading from different source files
- Different source could have different patient counts

**Validation Needed**:
1. Verify pipeline is loading from same NHS source as reference spreadsheet
2. Check if there are multiple versions (provisional vs final)
3. Compare source file dates

### Hypothesis 3: Aggregation Logic Issues

**Evidence**:
- No trust-level aggregates (cancer_type IS NULL) exist in database
- Migration 005 should create these but doesn't appear to be running

**Validation Needed**:
1. Verify migration 005 has been applied
2. Check if migration runs during data load or separately
3. Test if manual aggregation produces expected results

---

## Detailed Test Results

### Test 1: Database Connection

```bash
docker exec supabase-db psql -U postgres -d postgres -c "SELECT 1"
```

**Result**: ✅ **PASSED** - Database accessible

### Test 2: Data Existence Check

```sql
SELECT COUNT(*), MIN(period), MAX(period)
FROM performance_data.cancer_target_metrics;
-- Result: 193,404 rows, periods from 2023-10 to 2025-08
```

**Result**: ✅ **PASSED** - Data exists for test period 2025-08

### Test 3: Trust-Level Aggregates

```sql
SELECT COUNT(*)
FROM performance_data.cancer_target_metrics
WHERE metric = 5 AND period = '2025-08' AND cancer_type IS NULL;
-- Result: 0
```

**Result**: ❌ **FAILED** - No aggregates found

### Test 4: RJ1 Data Accuracy

**NHS Reference** (from `Monthly-CSV.csv`):
- ALL CANCERS, ALL STAGES: 878 within / 90 after = 968 total (90.7%)

**Database**:
- Sum of all cancer types (ALL ROUTES): 936 within / 111 after = 1047 total (89.4%)

**Result**: ❌ **FAILED** - Values don't match

### Test 5: Cancer Type Counts

13 cancer types expected, 13 found in database.

**Result**: ✅ **PASSED** - Correct number of cancer types

### Test 6: Referral Route Filtering

Only "ALL ROUTES" found in database for RJ1.

**Result**: ✅ **PASSED** - Correct referral route filtering

### Test 7: Duplicate Rows

Each cancer type has exactly 1 row.

**Result**: ✅ **PASSED** - No unexpected duplicates

---

## Recommendations

### Immediate Actions (Today)

1. **Investigate ALL STAGES Filtering**
   ```bash
   cd pipelines/outcomes_data
   # Add debug logging to transforms.py:177-182
   # Re-run pipeline with logging enabled
   poetry run python -m outcomes_data.pipelines.cancer --period 2025-08
   ```

2. **Check Source Data**
   ```bash
   # Find actual source CSV being loaded
   find . -name "*5*.csv" -type f | head -5
   # Compare with reference: public_aggregated_spreadsheets/cancer/Monthly-CSV.csv
   ```

3. **Verify Migration 005**
   ```sql
   -- Check if view includes aggregation logic
   \d+ performance_data.metric_values_base

   -- Test manual aggregation
   SELECT org_code, SUM(within_target), SUM(outside_target)
   FROM performance_data.cancer_target_metrics
   WHERE metric = 5 AND period = '2025-08' AND referral_route = 'ALL ROUTES'
   GROUP BY org_code
   LIMIT 5;
   ```

### Short Term (This Week)

1. **Fix ALL STAGES Filtering**
   - Add verbose logging to transformation step
   - Verify column detection works correctly
   - Test on single org/period before full load

2. **Implement Trust-Level Aggregation**
   - Either in pipeline (during gold stage)
   - Or in database migration
   - Ensure rows created with cancer_type IS NULL

3. **Run Automated Tests**
   ```bash
   # Once fixes implemented
   ./run_validation_tests.sh --critical
   ```

### Medium Term (Next 2 Weeks)

1. **Expand Test Coverage**
   - RTT pipeline tests
   - Oversight framework tests
   - All cancer metrics (28-day, 62-day)

2. **Add Data Quality Checks**
   - Pre-load validation against reference spreadsheets
   - Post-load validation with automated tests
   - Alert on mismatches before promoting to production

3. **Documentation**
   - Document source data versions and lineage
   - Create troubleshooting runbook
   - Train team on validation process

---

## Files to Investigate

### Priority 1: Critical Path

1. **`pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py`**
   - Lines 177-182: ALL STAGES filtering logic
   - Lines 225-235: Aggregation logic
   - Lines 196-198: Percentage calculation

2. **`database/migrations/client_specific/005_add_cancer_trust_aggregates.sql`**
   - Lines 199-223: Trust-level aggregation CTE
   - Verify this creates rows where cancer_type IS NULL

3. **Source CSV Location**
   - Find actual source file being loaded
   - Compare structure with reference CSV
   - Check for provisional vs final versions

### Priority 2: Supporting Investigation

4. **`pipelines/outcomes_data/outcomes_data/data_sources/cancer/extractor.py`**
   - Lines 18-80: Header detection logic
   - Verify correct columns being read

5. **`pipelines/outcomes_data/outcomes_data/data_sources/cancer/scraper.py`**
   - Lines 102-130: File selection logic
   - Check if downloading correct source

---

## Next Steps

1. ✅ **Tests created and infrastructure ready**
2. ⏳ **Run diagnostic investigation** (use commands above)
3. ⏳ **Fix data loading issues**
4. ⏳ **Re-run tests to verify fixes**
5. ⏳ **Expand test coverage**

---

## Test Automation Status

### Implemented ✅

- Test infrastructure (`test_utils.py`)
- Pytest configuration (`conftest.py`, `pytest.ini`)
- Cancer pipeline tests (`test_cancer_pipeline.py`)
- Quick validation script (`validate_quick.py`)
- Test runner script (`run_validation_tests.sh`)

### Pending ⏳

- Fix database connection issues (Supavisor tenant authentication)
- RTT pipeline tests
- Oversight framework tests
- Database aggregation tests (Layer 2)
- Tool output tests (Layer 3)
- End-to-end integration tests (Layer 4)
- CI/CD integration

---

## Contact

For questions about these test results:
- **Pipeline Issues**: See `NHS_PIPELINE_ANALYSIS.md`
- **SQL Diagnostics**: See `NHS_DEBUGGING_GUIDE.md`
- **Test Expansion**: See `TESTING_PLAN.md`

**Remember**: The tests are working correctly - they've successfully identified data quality issues. Now we need to fix the pipeline.
