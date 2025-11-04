"""Test cancer data pipeline against NHS published data.

These tests validate that cancer_target_metrics table matches NHS published spreadsheets.
"""
import pytest
import pandas as pd
from validation.test_utils import format_comparison_result


@pytest.mark.layer1
@pytest.mark.cancer
@pytest.mark.critical
class TestCancerPipelineData:
    """Validate cancer_target_metrics table against published data."""

    def test_metric_5_trust_level_aggregates(
        self, reference_loader, db_engine, value_comparator, test_period
    ):
        """
        CRITICAL: Verify trust-level aggregates match published totals.
        
        This test catches the 88% vs 90.7% bug by validating that:
        1. Trust-level aggregates exist (cancer_type IS NULL, referral_route = 'ALL ROUTES')
        2. They match the "ALL CANCERS" + "ALL STAGES" rows from NHS spreadsheet
        
        This is the PRIMARY test for validating tool output accuracy.
        """
        # Load reference data for ALL CANCERS + ALL STAGES
        ref_df = reference_loader.load_cancer_reference(period=test_period)
        ref_total = ref_df[
            (ref_df['Standard_or_Item'] == '31D') &
            (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES') &
            (ref_df['Cancer_Type'] == 'ALL CANCERS')
        ].copy()

        if ref_total.empty:
            pytest.skip(f"No reference data found for period {test_period}")

        # Load database aggregates
        query = """
            SELECT org_code, org_name, within_target, outside_target, pct_within_target
            FROM performance_data.cancer_target_metrics
            WHERE metric = 5
              AND period = :period
              AND cancer_type IS NULL
              AND referral_route = 'ALL ROUTES'
        """
        db_df = pd.read_sql(query, db_engine, params={'period': test_period})

        # Compare each trust
        mismatches = []
        missing_orgs = []

        for _, ref_row in ref_total.iterrows():
            org_code = ref_row['Org_Code']
            
            # Skip national totals
            if org_code == '-' or org_code == 'TOTAL':
                continue
            
            db_row = db_df[db_df['org_code'] == org_code]

            if db_row.empty:
                missing_orgs.append(org_code)
                continue

            db_row = db_row.iloc[0]

            # Extract values
            ref_within = int(ref_row['Within'])
            ref_after = int(ref_row['After'])
            ref_total_count = int(ref_row['Total'])
            ref_pct = float(ref_row['Performance'])

            db_within = int(db_row['within_target'])
            db_after = int(db_row['outside_target'])
            db_total_count = db_within + db_after
            db_pct = float(db_row['pct_within_target'])

            # Compare with tolerance
            within_match, within_diff = value_comparator.compare_counts(ref_within, db_within)
            after_match, after_diff = value_comparator.compare_counts(ref_after, db_after)
            pct_match, pct_diff = value_comparator.compare_percentages(ref_pct, db_pct)

            if not (within_match and after_match and pct_match):
                mismatches.append(
                    format_comparison_result(
                        org_code=org_code,
                        metric_name='Cancer 31-day (ALL CANCERS aggregate)',
                        ref_value=ref_pct,
                        db_value=db_pct,
                        ref_numerator=ref_within,
                        db_numerator=db_within,
                        ref_denominator=ref_total_count,
                        db_denominator=db_total_count
                    )
                )

        # Report results
        if missing_orgs:
            print(f"\n⚠️  WARNING: {len(missing_orgs)} trusts missing from database:")
            for org in missing_orgs[:10]:
                print(f"   - {org}")

        if mismatches:
            print(f"\n❌ FAILURE: {len(mismatches)} trust-level aggregate mismatches found")
            print("\nFirst 10 mismatches:")
            for m in mismatches[:10]:
                print(f"\n  Trust: {m['org_code']}")
                print(f"    NHS Published: {m['ref_numerator']}/{m['ref_denominator']} = {m['ref_value']}")
                print(f"    Database:      {m['db_numerator']}/{m['db_denominator']} = {m['db_value']}")
                print(f"    Difference:    {m['diff']}")

        # Assert
        assert len(missing_orgs) == 0, (
            f"Found {len(missing_orgs)} trusts in NHS spreadsheet missing from database. "
            f"This indicates aggregation logic is not running or data load is incomplete."
        )

        assert len(mismatches) == 0, (
            f"Found {len(mismatches)} trust-level aggregate mismatches. "
            f"Check pipeline transforms (ALL STAGES filtering) and aggregation logic."
        )

    def test_metric_5_treatment_stage_filtering(
        self, reference_loader, db_engine, value_comparator, test_period
    ):
        """
        CRITICAL: Verify metric 5 (31-day) only includes "ALL STAGES" data.
        
        Issue: Pipeline must filter to ALL STAGES only, not FIRST or SUBSEQUENT.
        Location: transforms.py lines 177-182
        """
        # Load reference data filtered to 31D + ALL STAGES
        ref_df = reference_loader.load_cancer_reference(period=test_period)
        ref_31d = ref_df[
            (ref_df['Standard_or_Item'] == '31D') &
            (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES')
        ].copy()

        if ref_31d.empty:
            pytest.skip(f"No reference data found for period {test_period}")

        # Load database data for metric 5 (disaggregated by cancer type)
        query = """
            SELECT org_code, cancer_type, referral_route,
                   within_target, outside_target, pct_within_target
            FROM performance_data.cancer_target_metrics
            WHERE metric = 5
              AND period = :period
              AND cancer_type IS NOT NULL
              AND cancer_type != 'ALL CANCERS'
            ORDER BY org_code, cancer_type
        """
        db_df = pd.read_sql(query, db_engine, params={'period': test_period})

        if db_df.empty:
            pytest.fail("No disaggregated cancer data found in database for metric 5")

        # Sample validation: compare a few orgs/cancer types
        sample_size = min(50, len(ref_31d))
        sample_ref = ref_31d.sample(n=sample_size, random_state=42)

        mismatches = []

        for _, ref_row in sample_ref.iterrows():
            org_code = ref_row['Org_Code']
            cancer_type = ref_row['Cancer_Type']

            # Skip totals
            if org_code == '-' or org_code == 'TOTAL' or cancer_type == 'ALL CANCERS':
                continue

            # Find matching database row
            db_row = db_df[
                (db_df['org_code'] == org_code) &
                (db_df['cancer_type'] == cancer_type)
            ]

            if db_row.empty:
                # May be filtered out due to small sample size - not necessarily an error
                continue

            db_row = db_row.iloc[0]

            # Compare counts (must be exact for disaggregated data)
            ref_within = int(ref_row['Within'])
            ref_total = int(ref_row['Total'])

            db_within = int(db_row['within_target'])
            db_total = int(db_within + db_row['outside_target'])

            within_match, _ = value_comparator.compare_counts(ref_within, db_within)
            total_match, _ = value_comparator.compare_counts(ref_total, db_total)

            if not (within_match and total_match):
                mismatches.append({
                    'org_code': org_code,
                    'cancer_type': cancer_type,
                    'ref_within': ref_within,
                    'ref_total': ref_total,
                    'db_within': db_within,
                    'db_total': db_total
                })

        if mismatches:
            print(f"\n❌ FAILURE: {len(mismatches)} disaggregated data mismatches")
            print("\nFirst 5 mismatches:")
            for m in mismatches[:5]:
                print(f"  {m['org_code']} - {m['cancer_type']}")
                print(f"    NHS: {m['ref_within']}/{m['ref_total']}")
                print(f"    DB:  {m['db_within']}/{m['db_total']}")

        assert len(mismatches) == 0, (
            f"Found {len(mismatches)} mismatches in disaggregated cancer data. "
            f"Check that pipeline filters to 'ALL STAGES' only (transforms.py:177-182)"
        )

    def test_all_cancer_orgs_loaded(
        self, reference_loader, db_engine, test_period
    ):
        """Verify all trusts in reference data are loaded to database."""
        ref_df = reference_loader.load_cancer_reference(period=test_period)
        
        # Get unique org codes from reference (exclude totals)
        ref_orgs = set(
            ref_df[
                (ref_df['Org_Code'] != '-') &
                (ref_df['Org_Code'] != 'TOTAL')
            ]['Org_Code'].unique()
        )

        # Get unique org codes from database
        db_orgs = set(
            pd.read_sql(
                """SELECT DISTINCT org_code 
                   FROM performance_data.cancer_target_metrics 
                   WHERE period = :period AND metric = 5""",
                db_engine,
                params={'period': test_period}
            )['org_code']
        )

        missing = ref_orgs - db_orgs
        
        if missing:
            print(f"\n⚠️  {len(missing)} trusts missing from database:")
            for org in sorted(missing)[:20]:
                print(f"   - {org}")

        assert len(missing) == 0, (
            f"Found {len(missing)} trusts in NHS spreadsheet but not in database. "
            f"This indicates incomplete data load."
        )

    def test_metric_5_rj1_specific_case(
        self, reference_loader, db_engine, value_comparator, test_period
    ):
        """
        Test the specific bug report case: RJ1 trust, cancer 31-day.
        
        Expected: 90.7% (878/968)
        Previously returned: 88%
        """
        org_code = 'RJ1'

        # Load reference data
        ref_df = reference_loader.load_cancer_reference(period=test_period)
        ref_row = ref_df[
            (ref_df['Org_Code'] == org_code) &
            (ref_df['Standard_or_Item'] == '31D') &
            (ref_df['Cancer_Type'] == 'ALL CANCERS') &
            (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES')
        ]

        if ref_row.empty:
            pytest.skip(f"RJ1 trust data not found in reference for period {test_period}")

        ref_row = ref_row.iloc[0]
        expected_within = int(ref_row['Within'])
        expected_total = int(ref_row['Total'])
        expected_pct = float(ref_row['Performance'])

        # Query database
        query = """
            SELECT within_target, outside_target, pct_within_target
            FROM performance_data.cancer_target_metrics
            WHERE org_code = :org_code
              AND metric = 5
              AND period = :period
              AND cancer_type IS NULL
              AND referral_route = 'ALL ROUTES'
        """

        result = pd.read_sql(
            query, db_engine,
            params={'org_code': org_code, 'period': test_period}
        )

        assert not result.empty, (
            f"Trust-level aggregate not found for {org_code}. "
            f"Aggregation logic may not be running."
        )

        db_row = result.iloc[0]
        db_within = int(db_row['within_target'])
        db_total = int(db_within + db_row['outside_target'])
        db_pct = float(db_row['pct_within_target'])

        # Compare
        within_match, _ = value_comparator.compare_counts(expected_within, db_within)
        total_match, _ = value_comparator.compare_counts(expected_total, db_total)
        pct_match, pct_diff = value_comparator.compare_percentages(expected_pct, db_pct)

        error_msg = f"""
RJ1 Trust Cancer 31-Day Validation Failed:

Expected (NHS Published): {expected_within}/{expected_total} = {expected_pct:.1%}
Database:                 {db_within}/{db_total} = {db_pct:.1%}
Difference:               {pct_diff:.3%}

This is the specific bug case that was reported.
"""

        assert within_match and total_match and pct_match, error_msg


@pytest.mark.layer1
@pytest.mark.cancer
class TestCancerOtherMetrics:
    """Test other cancer metrics (28-day, 62-day)."""

    def test_metric_3_28_day_standard(
        self, reference_loader, db_engine, value_comparator, test_period
    ):
        """Validate 28-day FDS (Faster Diagnosis Standard) data."""
        # Load reference
        ref_df = reference_loader.load_cancer_reference(period=test_period)
        ref_fds = ref_df[
            (ref_df['Standard_or_Item'] == 'FDS') &
            (ref_df['Cancer_Type'] == 'ALL CANCERS') &
            (ref_df['Referral_Route_or_Stage'] == 'ALL ROUTES')
        ].copy()

        if ref_fds.empty:
            pytest.skip(f"No FDS reference data for period {test_period}")

        # Query database
        query = """
            SELECT org_code, within_target, outside_target, pct_within_target
            FROM performance_data.cancer_target_metrics
            WHERE metric = 3
              AND period = :period
              AND cancer_type IS NULL
              AND referral_route = 'ALL ROUTES'
        """
        db_df = pd.read_sql(query, db_engine, params={'period': test_period})

        # Sample validation
        sample_orgs = ref_fds['Org_Code'].sample(n=min(10, len(ref_fds)), random_state=42)
        mismatches = []

        for org_code in sample_orgs:
            if org_code == '-' or org_code == 'TOTAL':
                continue

            ref_row = ref_fds[ref_fds['Org_Code'] == org_code].iloc[0]
            db_row = db_df[db_df['org_code'] == org_code]

            if db_row.empty:
                continue

            db_row = db_row.iloc[0]

            ref_pct = float(ref_row['Performance'])
            db_pct = float(db_row['pct_within_target'])

            pct_match, pct_diff = value_comparator.compare_percentages(ref_pct, db_pct)

            if not pct_match:
                mismatches.append({
                    'org_code': org_code,
                    'ref_pct': f"{ref_pct:.1%}",
                    'db_pct': f"{db_pct:.1%}",
                    'diff': f"{pct_diff:.3%}"
                })

        if mismatches:
            print(f"\n❌ 28-day FDS mismatches: {len(mismatches)}")
            for m in mismatches:
                print(f"  {m}")

        assert len(mismatches) == 0, f"Found {len(mismatches)} 28-day FDS mismatches"

    def test_metric_8_62_day_standard(
        self, reference_loader, db_engine, value_comparator, test_period
    ):
        """Validate 62-day urgent referral standard data."""
        # Load reference
        ref_df = reference_loader.load_cancer_reference(period=test_period)
        ref_62d = ref_df[
            (ref_df['Standard_or_Item'] == '62D') &
            (ref_df['Cancer_Type'] == 'ALL CANCERS') &
            (ref_df['Referral_Route_or_Stage'] == 'ALL STAGES')
        ].copy()

        if ref_62d.empty:
            pytest.skip(f"No 62-day reference data for period {test_period}")

        # Query database
        query = """
            SELECT org_code, within_target, outside_target, pct_within_target
            FROM performance_data.cancer_target_metrics
            WHERE metric = 8
              AND period = :period
              AND cancer_type IS NULL
              AND referral_route = 'ALL ROUTES'
        """
        db_df = pd.read_sql(query, db_engine, params={'period': test_period})

        # Sample validation
        sample_orgs = ref_62d['Org_Code'].sample(n=min(10, len(ref_62d)), random_state=42)
        mismatches = []

        for org_code in sample_orgs:
            if org_code == '-' or org_code == 'TOTAL':
                continue

            ref_row = ref_62d[ref_62d['Org_Code'] == org_code]
            if ref_row.empty:
                continue
            ref_row = ref_row.iloc[0]

            db_row = db_df[db_df['org_code'] == org_code]
            if db_row.empty:
                continue
            db_row = db_row.iloc[0]

            ref_pct = float(ref_row['Performance'])
            db_pct = float(db_row['pct_within_target'])

            pct_match, pct_diff = value_comparator.compare_percentages(ref_pct, db_pct)

            if not pct_match:
                mismatches.append({
                    'org_code': org_code,
                    'ref_pct': f"{ref_pct:.1%}",
                    'db_pct': f"{db_pct:.1%}",
                    'diff': f"{pct_diff:.3%}"
                })

        if mismatches:
            print(f"\n❌ 62-day standard mismatches: {len(mismatches)}")
            for m in mismatches:
                print(f"  {m}")

        assert len(mismatches) == 0, f"Found {len(mismatches)} 62-day standard mismatches"
