#!/usr/bin/env python3
"""
Quick validation script to test the RJ1 31-day cancer metric issue.

Usage:
    cd pipelines/outcomes_data
    python validate_quick.py

This script compares the public NHS spreadsheet against database values
to identify the 88% vs 90.7% discrepancy.
"""

import pandas as pd
import os
from sqlalchemy import create_engine
from pathlib import Path


def get_db_engine():
    """Get database connection."""
    db_url = os.getenv(
        'DATABASE_URL',
        f"postgresql://postgres:{os.getenv('POSTGRES_PASSWORD', 'postgres')}@localhost:5432/postgres"
    )
    return create_engine(db_url)


def load_reference_cancer_data(period='2025-08'):
    """Load cancer reference spreadsheet."""
    csv_path = Path(__file__).parent / 'outcomes_data' / 'public_aggregated_spreadsheets' / 'cancer' / 'Monthly-CSV.csv'

    if not csv_path.exists():
        raise FileNotFoundError(f"Reference spreadsheet not found: {csv_path}")

    df = pd.read_csv(csv_path)

    # Filter to period (format: "01/08/2025" → "2025-08")
    if '/' in df['Period'].iloc[0]:
        # Convert DD/MM/YYYY to YYYY-MM
        df['period_parsed'] = pd.to_datetime(df['Period'], format='%d/%m/%Y').dt.strftime('%Y-%m')
    else:
        df['period_parsed'] = df['Period']

    df = df[df['period_parsed'] == period].copy()

    return df


def test_rj1_cancer_31day():
    """Test the specific RJ1 31-day issue."""

    print("=" * 80)
    print("QUICK VALIDATION: RJ1 Trust Cancer 31-Day Metric")
    print("=" * 80)
    print()

    # Load reference data
    print("[1/4] Loading NHS published spreadsheet...")
    try:
        ref_df = load_reference_cancer_data(period='2025-08')
        print(f"      ✓ Loaded {len(ref_df)} rows from public spreadsheet")
    except Exception as e:
        print(f"      ✗ Error loading reference data: {e}")
        return

    # Filter to RJ1, 31D, ALL CANCERS, ALL STAGES
    ref_row = ref_df[
        (ref_df['Org_Code'] == 'RJ1') &
        (ref_df['Standard_or_Item'] == '31D') &
        (ref_df['Cancer_Type'] == 'ALL CANCERS') &
        (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES')
    ]

    if ref_row.empty:
        print("      ✗ RJ1 31-day data not found in reference spreadsheet")
        return

    ref_row = ref_row.iloc[0]
    ref_within = int(ref_row['Within'])
    ref_total = int(ref_row['Total'])
    ref_pct = float(ref_row['Performance'])

    print(f"      ✓ Reference data: {ref_within}/{ref_total} = {ref_pct:.3%}")
    print()

    # Query database: disaggregated rows
    print("[2/4] Querying database disaggregated rows...")
    engine = get_db_engine()

    query_disagg = """
        SELECT
            cancer_type,
            referral_route,
            within_target,
            outside_target,
            pct_within_target
        FROM performance_data.cancer_target_metrics
        WHERE org_code = 'RJ1'
          AND metric = 5
          AND period = '2025-08'
          AND cancer_type IS NOT NULL
        ORDER BY cancer_type, referral_route
    """

    try:
        disagg_df = pd.read_sql(query_disagg, engine)
        print(f"      ✓ Found {len(disagg_df)} disaggregated rows")

        # Show sample
        if not disagg_df.empty:
            print(f"      Sample (first 3):")
            for _, row in disagg_df.head(3).iterrows():
                print(f"        - {row['cancer_type']}, {row['referral_route']}: "
                      f"{int(row['within_target'])}/{int(row['within_target'] + row['outside_target'])} "
                      f"= {row['pct_within_target']:.3%}")
    except Exception as e:
        print(f"      ✗ Error querying disaggregated data: {e}")
        return

    print()

    # Query database: trust-level aggregate
    print("[3/4] Querying database trust-level aggregate...")

    query_agg = """
        SELECT
            within_target,
            outside_target,
            pct_within_target
        FROM performance_data.cancer_target_metrics
        WHERE org_code = 'RJ1'
          AND metric = 5
          AND period = '2025-08'
          AND cancer_type IS NULL
          AND referral_route = 'ALL ROUTES'
    """

    try:
        agg_df = pd.read_sql(query_agg, engine)

        if agg_df.empty:
            print("      ✗ Trust-level aggregate NOT FOUND in database")
            print("      → This is likely the issue! Aggregates are missing.")
            db_within = None
            db_total = None
            db_pct = None
        else:
            agg_row = agg_df.iloc[0]
            db_within = int(agg_row['within_target'])
            db_total = int(db_within + agg_row['outside_target'])
            db_pct = float(agg_row['pct_within_target'])
            print(f"      ✓ Database aggregate: {db_within}/{db_total} = {db_pct:.3%}")
    except Exception as e:
        print(f"      ✗ Error querying aggregate data: {e}")
        return

    print()

    # Compare
    print("[4/4] Comparison Results")
    print("-" * 80)

    print(f"NHS Published:     {ref_within:>5}/{ref_total:>5} = {ref_pct:>6.1%}")

    if db_within is not None:
        print(f"Database Aggregate: {db_within:>5}/{db_total:>5} = {db_pct:>6.1%}")

        within_match = (ref_within == db_within)
        total_match = (ref_total == db_total)
        pct_diff = abs(ref_pct - db_pct)
        pct_match = pct_diff <= 0.001  # 0.1% tolerance

        print()
        print("Validation:")
        print(f"  Numerator (within):    {'✓ MATCH' if within_match else '✗ MISMATCH'}")
        print(f"  Denominator (total):   {'✓ MATCH' if total_match else '✗ MISMATCH'}")
        print(f"  Percentage:            {'✓ MATCH' if pct_match else '✗ MISMATCH'} (diff: {pct_diff:.3%})")

        if within_match and total_match and pct_match:
            print()
            print("✅ SUCCESS: Database matches published data!")
        else:
            print()
            print("❌ FAILURE: Database does NOT match published data")
            print()
            print("Possible causes:")
            print("  1. Pipeline did not filter to 'ALL STAGES' correctly (transforms.py:177-182)")
            print("  2. Aggregation logic is incorrect (005_add_cancer_trust_aggregates.sql)")
            print("  3. Materialized view needs refresh: REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;")
    else:
        print(f"Database Aggregate: NOT FOUND")
        print()
        print("❌ FAILURE: Trust-level aggregate missing from database")
        print()
        print("Possible causes:")
        print("  1. Aggregation logic not running (check 005_add_cancer_trust_aggregates.sql)")
        print("  2. Migration not applied")
        print("  3. Data load incomplete")

    print()

    # Check sum of disaggregated
    if not disagg_df.empty and db_within is not None:
        print("Additional Check: Sum of disaggregated rows")
        print("-" * 80)

        # Sum only ALL ROUTES rows (to avoid double-counting)
        sum_df = disagg_df[disagg_df['referral_route'] == 'ALL ROUTES']
        sum_within = sum_df['within_target'].sum()
        sum_total = (sum_df['within_target'] + sum_df['outside_target']).sum()

        print(f"Sum of disaggregated (ALL ROUTES only): {int(sum_within)}/{int(sum_total)}")
        print(f"Database aggregate:                     {db_within}/{db_total}")

        sum_match = (abs(sum_within - db_within) < 0.01) and (abs(sum_total - db_total) < 0.01)

        if sum_match:
            print("✓ Aggregation logic is working correctly")
        else:
            print("✗ Aggregation logic may be incorrect")

    print()
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Review NHS_PIPELINE_ANALYSIS.md for detailed data flow")
    print("  2. Review NHS_DEBUGGING_GUIDE.md for SQL diagnostic queries")
    print("  3. Review TESTING_PLAN.md for comprehensive test suite")
    print()


if __name__ == '__main__':
    test_rj1_cancer_31day()
