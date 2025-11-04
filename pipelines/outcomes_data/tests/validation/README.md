# NHS Outcomes Data Validation Tests

This directory contains automated tests to validate that NHS outcomes data matches published spreadsheets throughout the pipeline.

## Quick Start

### Run All Validation Tests

```bash
cd pipelines/outcomes_data
./run_validation_tests.sh
```

### Run Critical Tests Only

```bash
./run_validation_tests.sh --critical
```

### Run Specific Test Layers

```bash
# Layer 1: Pipeline output validation
./run_validation_tests.sh --layer1

# Cancer tests only
./run_validation_tests.sh --cancer
```

## Test Organization

### Test Layers

1. **Layer 1: Pipeline Output Validation** (`test_cancer_pipeline.py`)
   - Validates `cancer_target_metrics` table against NHS spreadsheets
   - Checks data extraction, transformation, and loading
   - **Critical test**: `test_metric_5_trust_level_aggregates` - catches the 88% vs 90.7% bug

2. **Layer 2: Database Aggregation Validation** (coming soon)
   - Validates view logic and aggregations
   - Checks percentile calculations

3. **Layer 3: Tool Output Validation** (coming soon)
   - Validates MCP tool outputs
   - Checks query logic and formatting

4. **Layer 4: End-to-End Integration** (coming soon)
   - Complete pipeline validation
   - Spreadsheet → Tool output verification

### Test Files

- `test_utils.py` - Shared utilities (ReferenceDataLoader, ValueComparator)
- `test_cancer_pipeline.py` - Cancer waiting times tests
- `conftest.py` - Pytest configuration and fixtures

## Configuration

### Environment Variables

```bash
# Database connection (required)
export DATABASE_URL="postgresql://postgres:password@localhost:5432/postgres"
# OR
export POSTGRES_PASSWORD="your-password"

# Test configuration (optional)
export TEST_PERIOD="2025-08"              # Period to test
export TEST_ORG_CODES="RJ1,RYJ,RA7"      # Specific trusts to test
```

### Reference Data

Tests load NHS published spreadsheets from:
```
pipelines/outcomes_data/outcomes_data/public_aggregated_spreadsheets/
├── cancer/
│   └── Monthly-CSV.csv
├── rtt/
│   └── 20250831-RTT-August-2025-full-extract.csv
└── oversight/
    ├── nhs-oversight-framework-acute-trust-data.csv
    ├── nhs-oversight-framework-ambulance-trust-data.csv
    └── nhs-oversight-framework-non-acute-hospital-trust-data.csv
```

## Test Markers

Run specific test categories using pytest markers:

```bash
cd pipelines/outcomes_data

# Critical tests only
poetry run pytest tests/validation/ -m critical

# Cancer tests
poetry run pytest tests/validation/ -m cancer

# Layer 1 tests
poetry run pytest tests/validation/ -m layer1

# Slow tests (excluded by default)
poetry run pytest tests/validation/ -m "not slow"
```

Available markers:
- `critical` - High-priority tests that catch major bugs
- `layer1`, `layer2`, `layer3`, `layer4` - Test layer classification
- `cancer`, `rtt`, `oversight` - Domain-specific tests
- `slow` - Tests that take >5 seconds

## Understanding Test Output

### Successful Test

```
✓ test_metric_5_trust_level_aggregates PASSED
```

### Failed Test

```
❌ FAILURE: 3 trust-level aggregate mismatches found

First 10 mismatches:

  Trust: RJ1
    NHS Published: 878/968 = 90.7%
    Database:      345/392 = 88.0%
    Difference:    2.7%
```

**Action**: Review the mismatch details and:
1. Check if aggregation logic is running
2. Verify ALL STAGES filtering (transforms.py:177-182)
3. Run SQL diagnostics (see NHS_DEBUGGING_GUIDE.md)

## Debugging Failed Tests

### 1. Check Database Connection

```bash
psql $DATABASE_URL -c "SELECT 1"
```

### 2. Verify Data is Loaded

```sql
SELECT metric, COUNT(*), MAX(period)
FROM performance_data.cancer_target_metrics
GROUP BY metric;
```

### 3. Check Trust-Level Aggregates Exist

```sql
SELECT COUNT(*)
FROM performance_data.cancer_target_metrics
WHERE metric = 5
  AND period = '2025-08'
  AND cancer_type IS NULL
  AND referral_route = 'ALL ROUTES';
```

Should return a count > 0. If 0, aggregation logic is not running.

### 4. Run Quick Validation Script

```bash
cd pipelines/outcomes_data
python validate_quick.py
```

This validates the specific RJ1 31-day case and shows detailed diagnostics.

## Test Data Requirements

Before running tests:

1. **Load data for test period**:
   ```bash
   poetry run python -m outcomes_data.pipelines.cancer --period 2025-08
   ```

2. **Refresh materialized views**:
   ```sql
   REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;
   ```

3. **Ensure reference spreadsheets are up-to-date**:
   - Download latest NHS published data
   - Place in `public_aggregated_spreadsheets/` directory

## CI/CD Integration

Tests can run automatically on:
- Push to repository
- Pull requests
- Scheduled data loads

See `.github/workflows/validate_nhs_data.yml` for CI configuration.

## Troubleshooting

### "FileNotFoundError: Reference spreadsheet not found"

Ensure reference spreadsheets are in the correct location:
```bash
ls -l pipelines/outcomes_data/outcomes_data/public_aggregated_spreadsheets/cancer/
```

### "No reference data found for period 2025-08"

Either:
- Reference spreadsheet doesn't contain this period
- Set `TEST_PERIOD` to match available data
- Update reference spreadsheet with latest NHS data

### "Trust-level aggregate not found"

Aggregation logic may not be running. Check:
1. Migration 005 is applied: `005_add_cancer_trust_aggregates.sql`
2. Pipeline creates aggregates during data load
3. Materialized view is refreshed after data load

## Writing New Tests

See `TESTING_PLAN.md` for detailed guidance on adding:
- RTT pipeline tests
- Oversight framework tests
- Database aggregation tests
- Tool output tests

## Success Criteria

Tests pass when:
- ✅ Numerators match exactly (±0 patients)
- ✅ Denominators match exactly (±0 patients)
- ✅ Percentages within 0.1 percentage points
- ✅ All trusts from spreadsheet are loaded
- ✅ Tool output traces back to exact spreadsheet row

## Support

- **Test failures**: Review test output and check NHS_DEBUGGING_GUIDE.md
- **Pipeline issues**: See NHS_PIPELINE_ANALYSIS.md section 4
- **Adding tests**: Follow examples in TESTING_PLAN.md sections 2-5

**Key Principle**: If the test fails, the data is wrong. Never adjust tests to match incorrect data.
