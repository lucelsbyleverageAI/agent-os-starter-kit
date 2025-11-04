# NHS Outcomes Data Validation Testing Plan

## Executive Summary

This document outlines a comprehensive testing strategy to validate that:
1. **Pipeline output** matches NHS published spreadsheets (data integrity)
2. **Tool output** matches NHS published spreadsheets (query accuracy)
3. **Automated tests** catch discrepancies before production deployment

### Root Cause of 88% vs 90.7% Discrepancy

Based on analysis, the discrepancy stems from **different aggregation levels**:
- **88%**: Likely a disaggregated metric (specific cancer type or referral route, ~100-200 patients)
- **90.7%**: Trust-level aggregate across ALL cancer types (968 total patients: 878 within, 90 after)

The tool correctly queries for trust-level aggregates, so if it shows 88%, there's likely a data loading or aggregation issue.

---

## Testing Strategy Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Testing Layers                           │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Pipeline Output Validation                        │
│   → Compare: public_spreadsheets → database tables          │
│   → Validates: extraction, transformation, loading          │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Database Aggregation Validation                   │
│   → Compare: database tables → database views               │
│   → Validates: view logic, aggregation, percentiles         │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Tool Output Validation                             │
│   → Compare: database views → tool output                   │
│   → Validates: query logic, formatting, display             │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: End-to-End Integration Tests                      │
│   → Compare: public_spreadsheets → tool output              │
│   → Validates: complete pipeline integrity                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Test Implementation Plan

### Phase 1: Set Up Testing Infrastructure (Week 1)

#### 1.1 Create Test Utilities Module

**File**: `pipelines/outcomes_data/tests/validation/test_utils.py`

**Purpose**: Shared utilities for loading reference data and comparing values

```python
"""Utilities for validation testing."""
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
from sqlalchemy import create_engine

class ReferenceDataLoader:
    """Load NHS published spreadsheets as reference data."""

    def __init__(self, spreadsheets_dir: str):
        self.spreadsheets_dir = Path(spreadsheets_dir)

    def load_cancer_reference(self, period: str) -> pd.DataFrame:
        """Load cancer reference data for a specific period."""
        # Load from public_aggregated_spreadsheets/cancer/Monthly-CSV.csv
        # Filter to period, standardize column names
        pass

    def load_rtt_reference(self, period: str) -> pd.DataFrame:
        """Load RTT reference data for a specific period."""
        pass

    def load_oversight_reference(self, period: str) -> pd.DataFrame:
        """Load oversight reference data for a specific period."""
        pass

class ValueComparator:
    """Compare numeric values with tolerance handling."""

    def __init__(self, rtol=1e-5, atol=1e-8):
        """
        Args:
            rtol: Relative tolerance (0.00001 = 0.001% difference)
            atol: Absolute tolerance (for values near zero)
        """
        self.rtol = rtol
        self.atol = atol

    def compare_percentages(self, val1: float, val2: float) -> Tuple[bool, float]:
        """
        Compare two percentage values.

        Returns:
            (is_match, difference)
        """
        diff = abs(val1 - val2)
        # Allow 0.1 percentage point difference (rounding tolerance)
        matches = diff <= 0.001  # 0.1% tolerance
        return matches, diff

    def compare_counts(self, val1: int, val2: int) -> Tuple[bool, int]:
        """
        Compare two count values (must be exact).

        Returns:
            (is_match, difference)
        """
        diff = abs(val1 - val2)
        matches = diff == 0
        return matches, diff

def get_db_connection():
    """Get database connection from environment."""
    import os
    from sqlalchemy import create_engine

    db_url = os.getenv('DATABASE_URL',
                      'postgresql://postgres:password@localhost:5432/postgres')
    return create_engine(db_url)
```

#### 1.2 Create Validation Test Suite Structure

```
pipelines/outcomes_data/tests/
├── validation/
│   ├── __init__.py
│   ├── test_utils.py              # Shared utilities
│   ├── test_cancer_pipeline.py     # Layer 1: Cancer pipeline tests
│   ├── test_rtt_pipeline.py        # Layer 1: RTT pipeline tests
│   ├── test_oversight_pipeline.py  # Layer 1: Oversight pipeline tests
│   ├── test_database_aggregations.py  # Layer 2: View tests
│   ├── test_tool_outputs.py        # Layer 3: MCP tool tests
│   └── test_end_to_end.py          # Layer 4: Integration tests
├── fixtures/
│   └── sample_data/                # Small sample datasets for unit tests
└── conftest.py                     # Pytest configuration
```

---

### Phase 2: Layer 1 Tests - Pipeline Output Validation

#### 2.1 Cancer Pipeline Tests

**File**: `pipelines/outcomes_data/tests/validation/test_cancer_pipeline.py`

**Test Cases**:

```python
"""Test cancer data pipeline against NHS published data."""
import pytest
import pandas as pd
from test_utils import ReferenceDataLoader, ValueComparator, get_db_connection

@pytest.fixture
def reference_loader():
    return ReferenceDataLoader('pipelines/outcomes_data/outcomes_data/public_aggregated_spreadsheets')

@pytest.fixture
def db_engine():
    return get_db_connection()

class TestCancerPipelineData:
    """Validate cancer_target_metrics table against published data."""

    def test_metric_5_treatment_stage_filtering(self, reference_loader, db_engine):
        """
        CRITICAL: Verify metric 5 (31-day) only includes "ALL STAGES" data.

        Issue: Pipeline must filter to ALL STAGES only, not FIRST or SUBSEQUENT.
        """
        # Load reference data filtered to 31D + ALL STAGES
        ref_df = reference_loader.load_cancer_reference(period='2025-08')
        ref_31d = ref_df[
            (ref_df['Standard_or_Item'] == '31D') &
            (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES')
        ]

        # Load database data for metric 5
        query = """
            SELECT org_code, cancer_type, referral_route,
                   within_target, outside_target, pct_within_target
            FROM performance_data.cancer_target_metrics
            WHERE metric = 5 AND period = '2025-08'
        """
        db_df = pd.read_sql(query, db_engine)

        # For each org in reference data, compare with database
        comparator = ValueComparator()
        mismatches = []

        for _, ref_row in ref_31d.iterrows():
            org_code = ref_row['Org_Code']
            cancer_type = ref_row['Cancer_Type']

            # Find matching database row
            db_row = db_df[
                (db_df['org_code'] == org_code) &
                (db_df['cancer_type'] == cancer_type)
            ]

            if db_row.empty:
                mismatches.append({
                    'org_code': org_code,
                    'cancer_type': cancer_type,
                    'issue': 'Missing in database'
                })
                continue

            db_row = db_row.iloc[0]

            # Compare counts
            ref_within = ref_row['Within']
            ref_after = ref_row['After']
            ref_pct = ref_row['Performance']

            within_match, within_diff = comparator.compare_counts(
                int(ref_within), int(db_row['within_target'])
            )
            after_match, after_diff = comparator.compare_counts(
                int(ref_after), int(db_row['outside_target'])
            )
            pct_match, pct_diff = comparator.compare_percentages(
                ref_pct, db_row['pct_within_target']
            )

            if not (within_match and after_match and pct_match):
                mismatches.append({
                    'org_code': org_code,
                    'cancer_type': cancer_type,
                    'ref_within': ref_within,
                    'db_within': db_row['within_target'],
                    'within_diff': within_diff,
                    'ref_after': ref_after,
                    'db_after': db_row['outside_target'],
                    'after_diff': after_diff,
                    'ref_pct': ref_pct,
                    'db_pct': db_row['pct_within_target'],
                    'pct_diff': pct_diff
                })

        # Assert no mismatches
        if mismatches:
            print("\n=== CANCER 31-DAY MISMATCHES ===")
            for m in mismatches[:10]:  # Show first 10
                print(m)

        assert len(mismatches) == 0, f"Found {len(mismatches)} mismatches in cancer 31-day data"

    def test_metric_5_trust_level_aggregates(self, reference_loader, db_engine):
        """
        Verify trust-level aggregates (cancer_type IS NULL) match published totals.

        This is what the tool queries for.
        """
        # Load reference data for ALL CANCERS + ALL STAGES
        ref_df = reference_loader.load_cancer_reference(period='2025-08')
        ref_total = ref_df[
            (ref_df['Standard_or_Item'] == '31D') &
            (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES') &
            (ref_df['Cancer_Type'] == 'ALL CANCERS')
        ]

        # Load database aggregates
        query = """
            SELECT org_code, within_target, outside_target, pct_within_target
            FROM performance_data.cancer_target_metrics
            WHERE metric = 5
              AND period = '2025-08'
              AND cancer_type IS NULL
              AND referral_route = 'ALL ROUTES'
        """
        db_df = pd.read_sql(query, db_engine)

        # Compare each trust
        comparator = ValueComparator()
        mismatches = []

        for _, ref_row in ref_total.iterrows():
            org_code = ref_row['Org_Code']
            db_row = db_df[db_df['org_code'] == org_code]

            if db_row.empty:
                mismatches.append({
                    'org_code': org_code,
                    'issue': 'Trust-level aggregate missing in database'
                })
                continue

            db_row = db_row.iloc[0]

            # Compare
            ref_pct = ref_row['Performance']
            pct_match, pct_diff = comparator.compare_percentages(
                ref_pct, db_row['pct_within_target']
            )

            if not pct_match:
                mismatches.append({
                    'org_code': org_code,
                    'ref_pct': f"{ref_pct:.1%}",
                    'db_pct': f"{db_row['pct_within_target']:.1%}",
                    'diff': f"{pct_diff:.3%}",
                    'ref_within': ref_row['Within'],
                    'db_within': db_row['within_target'],
                    'ref_total': ref_row['Total'],
                    'db_total': db_row['within_target'] + db_row['outside_target']
                })

        # Report
        if mismatches:
            print("\n=== TRUST-LEVEL AGGREGATE MISMATCHES ===")
            for m in mismatches[:10]:
                print(m)

        assert len(mismatches) == 0, f"Found {len(mismatches)} trust-level aggregate mismatches"

    def test_metric_3_28_day_standard(self, reference_loader, db_engine):
        """Validate 28-day FDS (Faster Diagnosis Standard) data."""
        # Similar pattern to metric 5 tests
        pass

    def test_metric_8_62_day_standard(self, reference_loader, db_engine):
        """Validate 62-day urgent referral standard data."""
        pass

    def test_all_orgs_loaded(self, reference_loader, db_engine):
        """Verify all trusts in reference data are loaded to database."""
        ref_df = reference_loader.load_cancer_reference(period='2025-08')
        ref_orgs = set(ref_df['Org_Code'].unique())

        db_orgs = pd.read_sql(
            "SELECT DISTINCT org_code FROM performance_data.cancer_target_metrics WHERE period = '2025-08'",
            db_engine
        )['org_code'].unique()

        missing = ref_orgs - set(db_orgs)
        assert len(missing) == 0, f"Missing orgs in database: {missing}"

    def test_no_extra_orgs_in_database(self, reference_loader, db_engine):
        """Verify database doesn't contain orgs not in reference data."""
        ref_df = reference_loader.load_cancer_reference(period='2025-08')
        ref_orgs = set(ref_df['Org_Code'].unique())

        db_orgs = pd.read_sql(
            "SELECT DISTINCT org_code FROM performance_data.cancer_target_metrics WHERE period = '2025-08'",
            db_engine
        )['org_code'].unique()

        extra = set(db_orgs) - ref_orgs
        assert len(extra) == 0, f"Extra orgs in database: {extra}"
```

#### 2.2 RTT Pipeline Tests

**File**: `pipelines/outcomes_data/tests/validation/test_rtt_pipeline.py`

Similar structure testing `rtt_metrics_gold` table against RTT reference spreadsheet.

#### 2.3 Oversight Pipeline Tests

**File**: `pipelines/outcomes_data/tests/validation/test_oversight_pipeline.py`

Similar structure testing `oversight_metrics_raw` and `oversight_league_table_raw` against oversight reference spreadsheet.

---

### Phase 3: Layer 2 Tests - Database Aggregation Validation

#### 3.1 View Aggregation Tests

**File**: `pipelines/outcomes_data/tests/validation/test_database_aggregations.py`

```python
"""Test database view logic and aggregations."""
import pytest
import pandas as pd
from test_utils import get_db_connection, ValueComparator

class TestMetricValuesBaseView:
    """Validate metric_values_base view aggregation logic."""

    def test_cancer_trust_aggregates_match_sum(self, db_engine):
        """
        Verify trust-level aggregates equal sum of disaggregated rows.

        For each trust and period:
        - Sum all cancer_type-specific rows (where cancer_type IS NOT NULL)
        - Compare with trust-level aggregate row (where cancer_type IS NULL)
        """
        query = """
            WITH disaggregated AS (
                SELECT
                    period, metric, org_code,
                    SUM(within_target) as sum_within,
                    SUM(outside_target) as sum_outside
                FROM performance_data.cancer_target_metrics
                WHERE metric = 5
                  AND period = '2025-08'
                  AND cancer_type IS NOT NULL
                  AND referral_route = 'ALL ROUTES'
                GROUP BY period, metric, org_code
            ),
            aggregated AS (
                SELECT
                    period, metric, org_code,
                    within_target as agg_within,
                    outside_target as agg_outside
                FROM performance_data.cancer_target_metrics
                WHERE metric = 5
                  AND period = '2025-08'
                  AND cancer_type IS NULL
                  AND referral_route = 'ALL ROUTES'
            )
            SELECT
                d.org_code,
                d.sum_within,
                a.agg_within,
                d.sum_outside,
                a.agg_outside,
                ABS(d.sum_within - a.agg_within) as within_diff,
                ABS(d.sum_outside - a.agg_outside) as outside_diff
            FROM disaggregated d
            JOIN aggregated a ON d.org_code = a.org_code
            WHERE ABS(d.sum_within - a.agg_within) > 0.01
               OR ABS(d.sum_outside - a.agg_outside) > 0.01
        """

        mismatches = pd.read_sql(query, db_engine)

        if not mismatches.empty:
            print("\n=== AGGREGATION MISMATCHES ===")
            print(mismatches.head(10))

        assert mismatches.empty, f"Found {len(mismatches)} aggregation mismatches"

    def test_percentiles_calculated_correctly(self, db_engine):
        """
        Verify percentile calculations in insight_metrics_long.

        Test that:
        - Higher values → higher percentiles (when higher_is_better = TRUE)
        - Lower values → higher percentiles (when higher_is_better = FALSE)
        """
        query = """
            SELECT
                metric_id,
                org_code,
                value,
                percentile_overall,
                higher_is_better
            FROM performance_data.insight_metrics_long
            WHERE metric_id = 'cancer_31d_pct_within_target'
              AND period = '2025-08'
              AND cancer_type IS NULL
            ORDER BY value
        """

        df = pd.read_sql(query, db_engine)

        # For cancer metrics, higher_is_better should be TRUE
        assert df['higher_is_better'].all(), "Cancer metrics should have higher_is_better=TRUE"

        # Verify percentiles increase with value
        for i in range(len(df) - 1):
            curr_val = df.iloc[i]['value']
            next_val = df.iloc[i + 1]['value']
            curr_pct = df.iloc[i]['percentile_overall']
            next_pct = df.iloc[i + 1]['percentile_overall']

            if next_val > curr_val:
                assert next_pct >= curr_pct, \
                    f"Percentile should increase when value increases: {curr_val}→{next_val} but {curr_pct}→{next_pct}"
```

---

### Phase 4: Layer 3 Tests - Tool Output Validation

#### 4.1 MCP Tool Tests

**File**: `pipelines/outcomes_data/tests/validation/test_tool_outputs.py`

```python
"""Test MCP tool outputs against database views."""
import pytest
from apps.mcp.src.mcp_server.tools.nhs_analytics.queries import get_comprehensive_performance
from test_utils import get_db_connection, ValueComparator

class TestGetComprehensiveTrustPerformanceTool:
    """Validate GetComprehensiveTrustPerformance tool outputs."""

    def test_cancer_metrics_match_database(self, db_engine):
        """
        Verify tool returns same values as direct database query.

        This catches issues in:
        - Tool filtering logic
        - Formatting/rounding
        - Data serialization
        """
        org_code = 'RJ1'  # Guy's and St Thomas'
        period = '2025-08'

        # Get tool output
        tool_result = get_comprehensive_performance(
            engine=db_engine,
            org_code=org_code,
            period=period,
            domains=['cancer']
        )

        # Get direct database query
        db_query = """
            SELECT
                metric_id,
                value,
                numerator,
                denominator
            FROM performance_data.insight_metrics_long
            WHERE org_code = :org_code
              AND period = :period
              AND domain = 'cancer'
              AND cancer_type IS NULL
              AND referral_route = 'ALL ROUTES'
        """

        db_df = pd.read_sql(db_query, db_engine, params={'org_code': org_code, 'period': period})

        # Compare
        comparator = ValueComparator()
        mismatches = []

        for _, db_row in db_df.iterrows():
            metric_id = db_row['metric_id']

            # Find in tool output
            tool_metric = next(
                (m for m in tool_result['cancer'] if m['metric_id'] == metric_id),
                None
            )

            if not tool_metric:
                mismatches.append({
                    'metric_id': metric_id,
                    'issue': 'Missing from tool output'
                })
                continue

            # Compare values
            pct_match, pct_diff = comparator.compare_percentages(
                db_row['value'], tool_metric['value']
            )

            if not pct_match:
                mismatches.append({
                    'metric_id': metric_id,
                    'db_value': db_row['value'],
                    'tool_value': tool_metric['value'],
                    'diff': pct_diff
                })

        assert len(mismatches) == 0, f"Tool output mismatches: {mismatches}"

    def test_tool_specific_example_rj1_31day(self, db_engine):
        """
        Test the specific example from the bug report.

        RJ1 trust, cancer 31-day, should be 90.7% not 88%.
        """
        org_code = 'RJ1'
        period = '2025-08'

        tool_result = get_comprehensive_performance(
            engine=db_engine,
            org_code=org_code,
            period=period,
            domains=['cancer']
        )

        # Find 31-day metric
        cancer_31d = next(
            (m for m in tool_result['cancer']
             if m['metric_id'] == 'cancer_31d_pct_within_target'
             and m.get('cancer_type') is None),
            None
        )

        assert cancer_31d is not None, "Cancer 31-day metric not found in tool output"

        # Check values
        expected_within = 878
        expected_total = 968
        expected_pct = 878 / 968  # 0.907

        assert cancer_31d['numerator'] == expected_within, \
            f"Expected numerator {expected_within}, got {cancer_31d['numerator']}"

        assert cancer_31d['denominator'] == expected_total, \
            f"Expected denominator {expected_total}, got {cancer_31d['denominator']}"

        comparator = ValueComparator()
        pct_match, pct_diff = comparator.compare_percentages(expected_pct, cancer_31d['value'])

        assert pct_match, \
            f"Expected percentage {expected_pct:.1%}, got {cancer_31d['value']:.1%} (diff: {pct_diff:.3%})"
```

---

### Phase 5: Layer 4 Tests - End-to-End Integration

#### 5.1 Integration Tests

**File**: `pipelines/outcomes_data/tests/validation/test_end_to_end.py`

```python
"""End-to-end integration tests comparing public spreadsheets to tool outputs."""
import pytest
from test_utils import ReferenceDataLoader, ValueComparator, get_db_connection
from apps.mcp.src.mcp_server.tools.nhs_analytics.queries import get_comprehensive_performance

class TestEndToEndValidation:
    """Complete pipeline validation from source to tool output."""

    def test_cancer_end_to_end_sample_trusts(self):
        """
        Test complete flow for a sample of trusts:
        Public Spreadsheet → Pipeline → Database → Tool → Output
        """
        ref_loader = ReferenceDataLoader('pipelines/outcomes_data/outcomes_data/public_aggregated_spreadsheets')
        db_engine = get_db_connection()
        comparator = ValueComparator()

        # Test sample of trusts
        test_trusts = ['RJ1', 'RYJ', 'RA7']  # Guy's, Chelsea & Westminster, etc.
        period = '2025-08'

        for org_code in test_trusts:
            # Load reference data
            ref_df = ref_loader.load_cancer_reference(period=period)
            ref_31d = ref_df[
                (ref_df['Org_Code'] == org_code) &
                (ref_df['Standard_or_Item'] == '31D') &
                (ref_df['Cancer_Type'] == 'ALL CANCERS') &
                (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES')
            ]

            if ref_31d.empty:
                continue

            ref_row = ref_31d.iloc[0]
            ref_pct = ref_row['Performance']
            ref_within = ref_row['Within']
            ref_total = ref_row['Total']

            # Get tool output
            tool_result = get_comprehensive_performance(
                engine=db_engine,
                org_code=org_code,
                period=period,
                domains=['cancer']
            )

            # Find 31-day metric
            tool_31d = next(
                (m for m in tool_result['cancer']
                 if m['metric_id'] == 'cancer_31d_pct_within_target'
                 and m.get('cancer_type') is None),
                None
            )

            assert tool_31d is not None, f"Tool output missing 31-day metric for {org_code}"

            # Compare
            pct_match, pct_diff = comparator.compare_percentages(ref_pct, tool_31d['value'])

            assert pct_match, \
                f"""Trust {org_code} cancer 31-day mismatch:
                Reference: {ref_pct:.1%} ({ref_within}/{ref_total})
                Tool:      {tool_31d['value']:.1%} ({tool_31d['numerator']}/{tool_31d['denominator']})
                Diff:      {pct_diff:.3%}
                """
```

---

## Automated Test Execution

### Test Runner Script

**File**: `pipelines/outcomes_data/tests/run_validation.sh`

```bash
#!/bin/bash
# Run all validation tests and generate report

set -e

echo "=== NHS Outcomes Data Validation Suite ==="
echo "Starting at: $(date)"
echo ""

# Activate virtual environment
cd /Users/lucelsby/Documents/repos/e18/e18-agent-os/pipelines/outcomes_data
source .venv/bin/activate

# Set database connection
export DATABASE_URL="postgresql://postgres:${POSTGRES_PASSWORD}@localhost:5432/postgres"

# Run tests with verbose output and coverage
pytest tests/validation/ \
    -v \
    --tb=short \
    --html=test_results/validation_report.html \
    --self-contained-html \
    --cov=outcomes_data \
    --cov-report=html:test_results/coverage \
    --cov-report=term-missing

echo ""
echo "=== Test Results ==="
echo "HTML Report: test_results/validation_report.html"
echo "Coverage Report: test_results/coverage/index.html"
echo ""
echo "Completed at: $(date)"
```

### CI/CD Integration

**File**: `.github/workflows/validate_nhs_data.yml`

```yaml
name: NHS Data Validation

on:
  push:
    paths:
      - 'pipelines/outcomes_data/**'
      - 'database/migrations/client_specific/**'
      - 'apps/mcp/src/mcp_server/tools/nhs_analytics/**'
  pull_request:
    paths:
      - 'pipelines/outcomes_data/**'
      - 'database/migrations/client_specific/**'
      - 'apps/mcp/src/mcp_server/tools/nhs_analytics/**'

jobs:
  validate:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: supabase/postgres:15.8.1.060
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd pipelines/outcomes_data
          pip install poetry
          poetry install

      - name: Run database migrations
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/postgres
        run: |
          cd database
          python migrate.py

      - name: Load test data
        run: |
          cd pipelines/outcomes_data
          poetry run python -m outcomes_data.pipelines.cancer --period 2025-08

      - name: Run validation tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/postgres
        run: |
          cd pipelines/outcomes_data
          poetry run pytest tests/validation/ -v --html=test_results/validation_report.html

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: pipelines/outcomes_data/test_results/
```

---

## Manual Validation Procedures

### Quick Validation Checklist

For each new data period, run this checklist:

```bash
# 1. Load new period data
cd pipelines/outcomes_data
poetry run python -m outcomes_data.pipelines.cancer --period 2025-09
poetry run python -m outcomes_data.pipelines.rtt --period 2025-09
poetry run python -m outcomes_data.pipelines.oversight --period 2025-Q2

# 2. Refresh materialized view
psql -c "REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;"

# 3. Run validation tests
poetry run pytest tests/validation/ -v

# 4. Spot-check specific trust (manual verification)
psql <<EOF
SELECT
    metric_id,
    value,
    numerator,
    denominator
FROM performance_data.insight_metrics_long
WHERE org_code = 'RJ1'
  AND period = '2025-09'
  AND domain = 'cancer'
  AND cancer_type IS NULL
ORDER BY metric_id;
EOF

# 5. Compare with public spreadsheet (open in Excel/CSV viewer)
# - Check numerator/denominator match
# - Check percentage within 0.1% tolerance
```

### SQL Diagnostic Queries

**Check aggregation integrity**:
```sql
-- Verify trust aggregates equal sum of disaggregated rows
WITH disaggregated AS (
    SELECT
        org_code,
        SUM(within_target) as sum_within,
        SUM(within_target + outside_target) as sum_total
    FROM performance_data.cancer_target_metrics
    WHERE metric = 5
      AND period = '2025-08'
      AND cancer_type IS NOT NULL
      AND referral_route = 'ALL ROUTES'
    GROUP BY org_code
),
aggregated AS (
    SELECT
        org_code,
        within_target,
        within_target + outside_target as total
    FROM performance_data.cancer_target_metrics
    WHERE metric = 5
      AND period = '2025-08'
      AND cancer_type IS NULL
      AND referral_route = 'ALL ROUTES'
)
SELECT
    d.org_code,
    d.sum_within,
    a.within_target,
    d.sum_total,
    a.total,
    ABS(d.sum_within - a.within_target) as within_diff,
    ABS(d.sum_total - a.total) as total_diff
FROM disaggregated d
JOIN aggregated a USING (org_code)
WHERE ABS(d.sum_within - a.within_target) > 0.01
   OR ABS(d.sum_total - a.total) > 0.01;
```

---

## Success Criteria

Tests are considered passing when:

### Layer 1 (Pipeline Output):
- ✅ All trusts from public spreadsheet are loaded to database
- ✅ Numerators (within_target) match exactly (±0 patients)
- ✅ Denominators (total patients) match exactly (±0 patients)
- ✅ Percentages match within 0.1 percentage points
- ✅ No extra trusts in database that aren't in public data

### Layer 2 (Database Aggregations):
- ✅ Trust-level aggregates equal sum of disaggregated rows
- ✅ Percentiles rank correctly (higher value → higher percentile for positive metrics)
- ✅ Materialized views are up-to-date

### Layer 3 (Tool Output):
- ✅ Tool returns same values as direct database query
- ✅ No formatting/rounding errors beyond 0.1%
- ✅ Specific bug example (RJ1 31-day) shows 90.7% not 88%

### Layer 4 (End-to-End):
- ✅ Random sample of 10 trusts matches public spreadsheet
- ✅ All three domains (cancer, RTT, oversight) validate successfully
- ✅ Tool output can be traced back to exact source spreadsheet row

---

## Implementation Timeline

| Week | Tasks | Deliverables |
|------|-------|--------------|
| **Week 1** | Set up test infrastructure | test_utils.py, conftest.py, test runner script |
| **Week 2** | Implement Layer 1 tests (cancer) | test_cancer_pipeline.py with full test coverage |
| **Week 3** | Implement Layer 1 tests (RTT, oversight) | test_rtt_pipeline.py, test_oversight_pipeline.py |
| **Week 4** | Implement Layer 2 tests | test_database_aggregations.py |
| **Week 5** | Implement Layer 3 tests | test_tool_outputs.py |
| **Week 6** | Implement Layer 4 tests | test_end_to_end.py, CI/CD integration |
| **Week 7** | Run full validation on latest data | Test report, bug fixes |
| **Week 8** | Documentation and training | Runbooks, team training sessions |

---

## Next Steps

1. **Immediate (This Week)**:
   - [ ] Review this testing plan with team
   - [ ] Verify access to latest public spreadsheets in `public_aggregated_spreadsheets/`
   - [ ] Set up test database (copy of production or dedicated test instance)
   - [ ] Create test_utils.py module

2. **Short Term (Next 2 Weeks)**:
   - [ ] Implement critical test: `test_metric_5_trust_level_aggregates` (catches the 88% vs 90.7% bug)
   - [ ] Run manual validation on RJ1 trust to confirm fix
   - [ ] Document any schema or pipeline fixes discovered

3. **Medium Term (Next Month)**:
   - [ ] Complete all Layer 1-4 tests
   - [ ] Integrate with CI/CD pipeline
   - [ ] Add test monitoring dashboard

4. **Long Term (Ongoing)**:
   - [ ] Run validation tests before each production data load
   - [ ] Maintain reference spreadsheets (add new periods as published)
   - [ ] Monitor test failure trends to catch data quality issues

---

## Contact & Support

For questions about this testing plan:
- **Pipeline Issues**: Check `NHS_PIPELINE_ANALYSIS.md` for technical details
- **Debugging Help**: See `NHS_DEBUGGING_GUIDE.md` for SQL diagnostic queries
- **Test Failures**: Check test output HTML report and cross-reference with public spreadsheets

**Key Principle**: If the test fails, the data is wrong. Never adjust tests to match incorrect data.
