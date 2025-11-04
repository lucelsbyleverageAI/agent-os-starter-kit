# NHS Data Validation - Quick Start Guide

## What Was Built

A comprehensive 4-layer testing framework to ensure your NHS outcomes data pipeline produces accurate results that match published spreadsheets.

### The Problem We're Solving

Your tool showed **88%** for RJ1 trust cancer 31-day performance, but the NHS published spreadsheet shows **90.7%** (878 treated within 31 days out of 968 total patients).

This testing framework helps you:
1. **Detect** discrepancies between your data and NHS published data
2. **Diagnose** where in the pipeline the issue occurs
3. **Prevent** future data quality issues with automated tests

---

## Files Created

### Core Testing Infrastructure

```
pipelines/outcomes_data/
├── tests/
│   └── validation/
│       ├── __init__.py
│       ├── test_utils.py              # Data loading & comparison utilities
│       ├── test_cancer_pipeline.py    # Cancer validation tests
│       ├── conftest.py                # Pytest configuration
│       └── README.md                  # Detailed test documentation
├── pytest.ini                         # Pytest settings
├── run_validation_tests.sh            # Test runner script
└── validate_quick.py                  # Quick RJ1 diagnostic script
```

### Documentation

```
/ (repo root)
├── NHS_PIPELINE_ANALYSIS.md          # Technical analysis (19KB)
├── NHS_DEBUGGING_GUIDE.md            # SQL diagnostics (10KB)
└── TESTING_PLAN.md                   # Complete strategy (25KB)
```

---

## Running Your First Test

### Step 1: Diagnose the RJ1 Issue Right Now

```bash
cd /Users/lucelsby/Documents/repos/e18/e18-agent-os/pipelines/outcomes_data

# Set your database password
export POSTGRES_PASSWORD="your-password-here"

# Run the quick diagnostic
python validate_quick.py
```

**What it does**: Compares RJ1 trust 31-day data from your public spreadsheet against your database, showing exactly where the discrepancy is.

**Expected output**:
```
[1/4] Loading NHS published spreadsheet...
      ✓ Loaded 12,345 rows from public spreadsheet
      ✓ Reference data: 878/968 = 90.700%

[2/4] Querying database disaggregated rows...
      ✓ Found 45 disaggregated rows

[3/4] Querying database trust-level aggregate...
      ✓ Database aggregate: 878/968 = 90.700%

[4/4] Comparison Results
------------------------------------------------------
NHS Published:     878/968 = 90.7%
Database Aggregate: 878/968 = 90.7%

Validation:
  Numerator (within):    ✓ MATCH
  Denominator (total):   ✓ MATCH
  Percentage:            ✓ MATCH (diff: 0.000%)

✅ SUCCESS: Database matches published data!
```

**If it fails**, you'll see:
- Which values don't match
- Possible causes (filtering, aggregation, view refresh)
- Next steps to fix

---

### Step 2: Run Automated Test Suite

```bash
cd pipelines/outcomes_data

# Run critical tests only (fastest - catches major bugs)
./run_validation_tests.sh --critical

# OR run all cancer tests
./run_validation_tests.sh --cancer

# OR run everything
./run_validation_tests.sh
```

**What it tests**:
1. ✅ Trust-level aggregates match NHS published totals
2. ✅ Treatment stage filtering works correctly (ALL STAGES only)
3. ✅ All trusts from spreadsheet are loaded to database
4. ✅ RJ1 specific case (the reported bug)
5. ✅ 28-day and 62-day standards

**Test output**:
- Green ✓ = Pass
- Red ✗ = Fail with detailed mismatch information
- HTML report: `test_results/validation_report.html`

---

## Understanding Test Results

### ✅ All Tests Pass

```
================================================================
✓ All tests passed!
================================================================

Test report: test_results/validation_report.html
```

**Action**: Your data is accurate! Deploy with confidence.

---

### ❌ Test Failure Example

```
FAILED test_metric_5_trust_level_aggregates

❌ FAILURE: 3 trust-level aggregate mismatches found

First 10 mismatches:

  Trust: RJ1
    NHS Published: 878/968 = 90.7%
    Database:      345/392 = 88.0%
    Difference:    2.7%
```

**What this means**: Your database has different values than NHS published data.

**Common causes**:
1. **Filtering issue**: Pipeline not filtering to "ALL STAGES" (transforms.py:177-182)
2. **Aggregation missing**: Trust-level aggregates not being created
3. **Stale data**: Materialized view needs refresh

**How to fix**:

```bash
# Check if aggregates exist
psql $DATABASE_URL << 'EOF'
SELECT COUNT(*)
FROM performance_data.cancer_target_metrics
WHERE metric = 5
  AND period = '2025-08'
  AND cancer_type IS NULL;
EOF

# If count is 0, aggregation logic isn't running
# Check: database/migrations/client_specific/005_add_cancer_trust_aggregates.sql

# Refresh materialized view
psql $DATABASE_URL -c "REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;"

# Re-run tests
./run_validation_tests.sh --critical
```

---

## Next Steps

### Immediate (Today)

1. **Run the quick validation**:
   ```bash
   python validate_quick.py
   ```
   This will tell you if the RJ1 bug exists in your current data.

2. **If it fails, investigate**:
   - Check `NHS_DEBUGGING_GUIDE.md` section 2 for SQL queries
   - Look at transforms.py lines 177-182 (treatment stage filtering)
   - Verify aggregation logic in migration 005

3. **Fix and re-test**:
   ```bash
   ./run_validation_tests.sh --critical
   ```

### Short Term (This Week)

1. **Run tests on your latest data load**:
   ```bash
   # Load latest period
   poetry run python -m outcomes_data.pipelines.cancer --period 2025-09

   # Validate
   TEST_PERIOD=2025-09 ./run_validation_tests.sh --cancer
   ```

2. **Add to your data loading workflow**:
   - After each data load, run validation tests
   - Only promote to production if tests pass
   - Document any expected discrepancies

3. **Review documentation**:
   - `TESTING_PLAN.md` - Complete testing strategy
   - `NHS_PIPELINE_ANALYSIS.md` - Technical deep dive
   - `tests/validation/README.md` - Detailed test guide

### Medium Term (Next 2 Weeks)

1. **Implement remaining tests** (following TESTING_PLAN.md):
   - RTT pipeline tests
   - Oversight framework tests
   - Database aggregation tests (Layer 2)
   - Tool output tests (Layer 3)

2. **Set up CI/CD**:
   - Tests run automatically on data loads
   - Alerts on test failures
   - Prevents bad data reaching production

3. **Create validation dashboard**:
   - Track test pass rates over time
   - Visualize data quality metrics
   - Alert on trends

---

## Common Issues & Solutions

### Issue: "FileNotFoundError: Reference spreadsheet not found"

**Cause**: Public spreadsheet not in expected location.

**Solution**:
```bash
# Check file exists
ls -l pipelines/outcomes_data/outcomes_data/public_aggregated_spreadsheets/cancer/Monthly-CSV.csv

# If missing, download from NHS England and place there
```

---

### Issue: "No reference data found for period 2025-08"

**Cause**: Spreadsheet doesn't contain data for test period.

**Solution**:
```bash
# Check what periods are available
python -c "
import pandas as pd
df = pd.read_csv('outcomes_data/public_aggregated_spreadsheets/cancer/Monthly-CSV.csv')
print(df['Period'].unique()[:10])
"

# Set TEST_PERIOD to match available data
export TEST_PERIOD="2025-07"
./run_validation_tests.sh --critical
```

---

### Issue: "Trust-level aggregate not found"

**Cause**: Aggregation logic not creating trust-level rows.

**Solution**:
```sql
-- Check if migration 005 is applied
\d performance_data.cancer_target_metrics

-- Re-run migration if needed
cd database
python migrate.py

-- Reload data
cd pipelines/outcomes_data
poetry run python -m outcomes_data.pipelines.cancer --period 2025-08
```

---

## Test Markers & Filters

Run specific test subsets:

```bash
cd pipelines/outcomes_data

# Only critical tests (fastest)
./run_validation_tests.sh --critical

# Only Layer 1 tests (pipeline output)
./run_validation_tests.sh --layer1

# Only cancer tests
./run_validation_tests.sh --cancer

# Verbose output
./run_validation_tests.sh --verbose

# Custom pytest command
poetry run pytest tests/validation/ -m "cancer and critical" -v
```

---

## Architecture Summary

```
NHS Published Spreadsheet (source of truth)
    ↓
[Layer 1 Tests] ← test_cancer_pipeline.py
    ↓
cancer_target_metrics table
    ↓
[Layer 2 Tests] ← test_database_aggregations.py (coming soon)
    ↓
insight_metrics_long view
    ↓
[Layer 3 Tests] ← test_tool_outputs.py (coming soon)
    ↓
GetComprehensiveTrustPerformance tool
    ↓
[Layer 4 Tests] ← test_end_to_end.py (coming soon)
    ↓
Final validation ✓
```

**Current Status**: Layer 1 tests implemented and ready to run.

---

## Key Commands Reference

```bash
# Quick diagnostic (run first)
python validate_quick.py

# Run critical tests
./run_validation_tests.sh --critical

# Run all cancer tests
./run_validation_tests.sh --cancer

# Run all tests
./run_validation_tests.sh

# Check database connection
psql $DATABASE_URL -c "SELECT 1"

# Refresh materialized view
psql $DATABASE_URL -c "REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;"

# Load latest data
poetry run python -m outcomes_data.pipelines.cancer --period 2025-09
```

---

## Getting Help

- **Test failures**: Check `test_results/validation_report.html` and `NHS_DEBUGGING_GUIDE.md`
- **Pipeline issues**: See `NHS_PIPELINE_ANALYSIS.md` section 4 (Potential Sources of Discrepancies)
- **SQL diagnostics**: Use queries in `NHS_DEBUGGING_GUIDE.md` sections 2-8
- **Adding tests**: Follow examples in `TESTING_PLAN.md`

---

## Success Criteria

Your data is validated when:

- ✅ `validate_quick.py` shows all metrics match
- ✅ `run_validation_tests.sh --critical` passes all tests
- ✅ Numerators match exactly (±0 patients)
- ✅ Denominators match exactly (±0 patients)
- ✅ Percentages within 0.1 percentage points
- ✅ Tool output matches NHS published spreadsheet

**Remember**: If the test fails, the data is wrong. Never adjust tests to match incorrect data.

---

## What's Next?

1. Run `python validate_quick.py` right now
2. Fix any issues found
3. Run `./run_validation_tests.sh --critical`
4. Review `TESTING_PLAN.md` for expanding test coverage
5. Integrate into your data loading workflow

Good luck! 🚀
