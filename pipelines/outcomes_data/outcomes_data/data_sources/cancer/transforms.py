from __future__ import annotations
import pandas as pd
import re

def _slugify(text: str) -> str:
    """Convert a string into a snake_case slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text) # remove special chars
    text = re.sub(r'[\s-]+', '_', text) # replace spaces and hyphens with underscores
    return text.strip('_')

def _clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten multi-level headers and clean column names, ensuring uniqueness.

    Handles both multi-level headers (MultiIndex with tuples) and single-level headers (Index with strings).
    """
    # CRITICAL FIX: Detect whether columns are MultiIndex (tuple-based) or simple Index (string-based)
    # Without this check, single-level headers like "Within_31_days" get mangled to "w_i_3"
    # because col[0] and col[1] extract the first two characters instead of tuple elements
    is_multi_index = isinstance(df.columns, pd.MultiIndex)

    new_cols = []
    col_counts = {}
    for col in df.columns:
        if is_multi_index:
            # Multi-level: col is a tuple like ('PARENT', 'CHILD')
            level1 = str(col[0]) if pd.notna(col[0]) else ''
            level2 = str(col[1]) if pd.notna(col[1]) else ''
        else:
            # Single-level: col is a string, use it directly
            level1 = str(col) if pd.notna(col) else ''
            level2 = ''

        if 'unnamed:' in level1.lower(): level1 = ''
        if 'unnamed:' in level2.lower(): level2 = ''

        parts = [part for part in [level1, level2] if part]

        if not parts:
            new_cols.append(f"to_drop_{len(new_cols)}")
            continue

        slug = _slugify(" ".join(parts))

        if slug in col_counts:
            col_counts[slug] += 1
            slug = f"{slug}_{col_counts[slug]}"
        else:
            col_counts[slug] = 1

        new_cols.append(slug)

    df.columns = new_cols

    cols_to_drop = [c for c in df.columns if c.startswith('to_drop_')]
    if ' ' in df.columns:
        cols_to_drop.append(' ')
    if '' in df.columns:
        cols_to_drop.append('')

    df = df.drop(columns=cols_to_drop, errors='ignore')
    return df

def load_bronze(csv_path: str, header_idx: int, encoding: str) -> pd.DataFrame:
    """Load the raw CSV into a DataFrame, creating a multi-level header."""
    header_spec = [header_idx - 1, header_idx] if header_idx > 0 else 0
    df = pd.read_csv(
        csv_path,
        encoding=encoding,
        header=header_spec,
        skip_blank_lines=True,
    )
    return df

def build_silver(bronze_df: pd.DataFrame, period: str, metric: int) -> pd.DataFrame:
    """Clean and structure the bronze data."""
    if bronze_df.empty:
        return pd.DataFrame()

    import logging
    logger = logging.getLogger(__name__)

    # DEBUG: Log bronze column structure
    logger.debug(f"Bronze DataFrame columns type: {type(bronze_df.columns)}")
    logger.debug(f"Is MultiIndex: {isinstance(bronze_df.columns, pd.MultiIndex)}")
    logger.debug(f"First 5 bronze columns: {list(bronze_df.columns[:5])}")

    df = _clean_column_names(bronze_df.copy())

    # DEBUG: Log cleaned column names
    logger.debug(f"First 15 cleaned columns: {list(df.columns[:15])}")

    # DEBUG: For metric 5, show a sample row with RJ1 Breast
    if metric == 5 and len(df) > 0:
        sample_row = df[df.iloc[:, 0].astype(str).str.contains('RJ1', case=False, na=False)]
        if len(sample_row) > 0:
            first_sample = sample_row.iloc[0]
            logger.debug(f"Sample RJ1 row columns: {list(df.columns)}")
            logger.debug(f"Sample RJ1 row values (first 20 cols): {list(first_sample[:20])}")

    df = df.dropna(how='all')

    # Filter out header/metadata rows - look for actual ODS codes in the first column
    # ODS codes are typically 3-letter codes like RCF, RTK, etc.
    if len(df.columns) > 0:
        first_col = df.columns[0]
        # Keep rows where first column looks like an ODS code (3-4 letters/numbers)
        # and doesn't contain metadata keywords
        def is_data_row(val):
            if pd.isna(val):
                return False
            val_str = str(val).strip()
            # Filter out obvious metadata (case-insensitive)
            val_upper = val_str.upper()
            if any(keyword in val_upper for keyword in [
                'BASIS:', 'DEFINITIONS:', 'FOUR WEEK', 'OCT-', 'JUL-', 'APR-', 'JAN-',
                'NUMBER OF PEOPLE', 'PERCENTAGE', 'ODS CODE', 'ACCOUNTABLE', 'REFERRAL',
                'SUSPECTED CANCER', 'TOTAL', 'WITHIN', 'AFTER'
            ]):
                return False
            # Keep rows that look like ODS codes (typically 3-4 character codes)
            # ODS codes are alphanumeric and reasonably short
            return (len(val_str) >= 2 and len(val_str) <= 6 and
                    val_str.replace(' ', '').isalnum() and
                    not val_str.isdigit())  # Exclude pure numbers

        df = df[df[first_col].apply(is_data_row)]

    df['period'] = period
    df['metric'] = metric

    for col in df.columns:
        if 'total' in col or 'within' in col or 'after' in col or 'number' in col:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        if 'percentage' in col or 'told_within' in col:
             df[col] = pd.to_numeric(df[col], errors='coerce')

    return df

def compute_gold(silver_df: pd.DataFrame) -> pd.DataFrame:
    """For cancer, gold is the same as silver as it's already granular."""
    return silver_df


def build_target_gold(silver_df: pd.DataFrame) -> pd.DataFrame:
    """Produce unified target metrics per org and cancer type.

    Output columns:
      - period: YYYY-MM
      - metric: 3|5|8
      - metric_label: human-readable label for the metric window
      - org_code: provider code
      - org_name: provider name
      - cancer_type: cancer type/site
      - referral_route: referral route (e.g. ALL ROUTES, URGENT SUSPECTED CANCER)
      - within_target: numeric count
      - outside_target: numeric count
      - pct_within_target: float 0..1

    Rules:
      - Break down by referral_route when present (including ALL ROUTES rows).
      - Map within/outside/pct columns depending on metric (28d, 31d, 62d).
      - If percentage not present, compute from counts; if counts missing but percentage and total present, derive counts.
    """
    if silver_df.empty:
        return pd.DataFrame(columns=[
            "period", "metric", "org_code", "org_name", "cancer_type",
            "within_target", "outside_target", "pct_within_target",
        ])

    df = silver_df.copy()

    # Column name helpers
    cols = set(df.columns)
    def first_existing(names: list[str]) -> str | None:
        for n in names:
            if n in cols:
                return n
        return None

    metric_val = int(df["metric"].iloc[0]) if "metric" in df.columns and len(df) else None

    # Identify common dimension columns
    org_code_col = first_existing(["ods_code_1", "ods_code", "org_code"]) or "ods_code_1"
    org_name_col = first_existing(["accountable_provider", "provider", "org_name"]) or "accountable_provider"
    cancer_type_col = first_existing(["cancer_type_3", "suspected_cancer_or_breast_symptomatic_2", "cancer_type"]) or "cancer_type_3"

    # CRITICAL FIX: CSV column "Referral_Route_or_Stage" contains BOTH route and stage info
    # After slugification and processing, it may become various column names depending on the metric
    # Common variations: "referral_route_or_stage", "treatment_stage", "referral_route", "stageroute", "stage_route"
    # This column contains values like: "ALL STAGES", "FIRST TREATMENTS", "SUBSEQUENT TREATMENTS" (for 31-day)
    # Or route values like: "ALL ROUTES", "URGENT SUSPECTED CANCER", etc. (for other metrics)
    route_or_stage_col = first_existing([
        "referral_route_or_stage",
        "treatment_stage",  # Common for metric 5
        "referral_route",
        "stageroute",
        "stage_route"
    ])

    # For metrics where this is a referral route, use it as route_col
    route_col = route_or_stage_col

    # For metrics where this is a treatment stage (31-day), also use it as treatment_stage_col
    treatment_stage_col = route_or_stage_col if metric_val == 5 else None

    # Choose metric-specific field names
    if metric_val == 8:
        within_col = first_existing(["within_62_days"])  # count
        outside_col = first_existing(["after_62_days"])  # count
        pct_col = first_existing(["percentage_treated_within_62_days"])  # fraction
        total_col = first_existing(["number_of_people_receiving_treatment_for_cancer_total", "total"])
    elif metric_val == 5:
        within_col = first_existing(["within_31_days", "treated_within_31_days"])  # count
        outside_col = first_existing(["after_31_days"])  # count
        pct_col = first_existing(["percentage_treated_within_31_days"])  # fraction if present
        total_col = first_existing(["number_of_people_receiving_treatment_for_cancer_total", "total"])
    elif metric_val == 3:
        within_col = first_existing(["within_28_days"])  # count
        outside_col = first_existing(["after_28_days"])  # count
        pct_col = first_existing(["told_within_28_days", "percentage_told_within_28_days"])  # fraction
        total_col = first_existing(["total", "number_of_people_told_cancer_diagnosis_outcome_total"])  # total records
    else:
        within_col = outside_col = pct_col = total_col = None

    # Validation logging for column selection
    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Column selection for metric {metric_val}:")
    logger.debug(f"  within_col: {within_col}")
    logger.debug(f"  outside_col: {outside_col}")
    logger.debug(f"  pct_col: {pct_col}")
    logger.debug(f"  total_col: {total_col}")

    # Critical validation: ensure required columns were found
    if within_col is None or outside_col is None:
        logger.warning(
            f"CRITICAL: Missing required columns for metric {metric_val}. "
            f"within_col={within_col}, outside_col={outside_col}. "
            f"Available columns: {sorted(df.columns.tolist())}"
        )

    # Keep all referral routes to provide breakdown (including 'ALL ROUTES' rows if present)

    # Filter for metric 5 (31-day): only keep "ALL STAGES" rows to match official NHS published data
    # The CSV contains separate rows for "ALL STAGES", "FIRST TREATMENTS", and "SUBSEQUENT TREATMENTS"
    # The official NHS England published 31-day metric uses "ALL STAGES" (includes both first and subsequent)
    # Using "FIRST TREATMENTS" only would undercount patients and give incorrect percentages
    if metric_val == 5:
        import logging
        logger = logging.getLogger(__name__)

        pre_filter_count = len(df)
        logger.info(f"Metric 5 (31-day) processing: treatment_stage_col='{treatment_stage_col}', rows before filter={pre_filter_count}")

        if treatment_stage_col is None:
            raise ValueError(
                f"CRITICAL: treatment_stage_col is None for metric 5. "
                f"Cannot filter to ALL STAGES rows. "
                f"Available columns: {sorted(cols)}"
            )

        if treatment_stage_col not in df.columns:
            raise ValueError(
                f"CRITICAL: treatment_stage_col '{treatment_stage_col}' not found in DataFrame. "
                f"Available columns: {sorted(df.columns.tolist())}"
            )

        # Log unique values before filtering
        unique_stages = df[treatment_stage_col].unique()
        logger.info(f"Unique treatment stage values before filter: {sorted(unique_stages)}")

        # Apply filter - normalize strings to handle any whitespace/case variations
        df = df[df[treatment_stage_col].astype(str).str.strip().str.upper() == "ALL STAGES"].copy()

        post_filter_count = len(df)
        logger.info(f"Rows after ALL STAGES filter: {post_filter_count} (removed {pre_filter_count - post_filter_count} rows)")

        # Defensive validation: filter MUST reduce row count
        if post_filter_count == 0:
            raise ValueError(
                f"CRITICAL: ALL STAGES filter removed ALL rows. "
                f"Pre-filter count: {pre_filter_count}. "
                f"Unique stage values were: {unique_stages}. "
                f"Check if 'ALL STAGES' value exists in source data."
            )

        if post_filter_count >= pre_filter_count:
            raise ValueError(
                f"CRITICAL: ALL STAGES filter did not reduce row count "
                f"({pre_filter_count} -> {post_filter_count}). "
                f"This suggests FIRST TREATMENTS and SUBSEQUENT TREATMENTS rows are not being filtered out. "
                f"Unique stage values were: {unique_stages}"
            )

        # Log sample of filtered data for verification
        if post_filter_count > 0:
            sample_df = df[[treatment_stage_col, cancer_type_col, within_col if within_col else "within_target"]].head(3)
            logger.info(f"Sample data after filter:\n{sample_df.to_string()}")

    # Derive within/outside/pct with fallbacks
    import numpy as np

    within = df[within_col] if within_col and within_col in df else None
    outside = df[outside_col] if outside_col and outside_col in df else None
    pct = df[pct_col] if pct_col and pct_col in df else None
    total = df[total_col] if total_col and total_col in df else None

    if within is None and pct is not None and total is not None:
        within = (pct.astype(float) * total.astype(float)).round()
    if outside is None and total is not None and within is not None:
        outside = (total.astype(float) - within.astype(float)).clip(lower=0)
    if pct is None and within is not None and outside is not None:
        denom = (within.astype(float) + outside.astype(float))
        pct = np.where(denom > 0, within.astype(float) / denom, np.nan)

    # Build minimal dataset
    # Metric label mapping
    metric_label = None
    if metric_val == 8:
        metric_label = "62_day_referral_to_treatment"
    elif metric_val == 5:
        metric_label = "31_day_decision_to_treat_to_treatment"
    elif metric_val == 3:
        metric_label = "28_day_faster_diagnosis"
    else:
        metric_label = "unknown"

    # Determine referral_route value
    # For metric 5 (31-day), route_col contains treatment stage values like "ALL STAGES"
    # We've already filtered to keep only "ALL STAGES" rows, so output should be "ALL ROUTES"
    # For other metrics, route_col contains actual referral routes, so use it directly
    if metric_val == 5:
        referral_route_value = "ALL ROUTES"
    elif route_col and route_col in df.columns:
        referral_route_value = df[route_col]
    else:
        referral_route_value = "ALL ROUTES"

    minimal = pd.DataFrame({
        "period": df["period"],
        "metric": df["metric"],
        "metric_label": metric_label,
        "org_code": df[org_code_col],
        "org_name": df[org_name_col],
        "cancer_type": df[cancer_type_col],
        "referral_route": referral_route_value,
        "within_target": within.astype(float) if within is not None else np.nan,
        "outside_target": outside.astype(float) if outside is not None else np.nan,
        "pct_within_target": pct.astype(float) if pct is not None else np.nan,
    })

    # Aggregate by org/type to ensure a single row per group
    grouped = (minimal
               .groupby(["period", "metric", "metric_label", "org_code", "org_name", "cancer_type", "referral_route"], as_index=False)
               .agg({
                   "within_target": "sum",
                   "outside_target": "sum",
                   # recompute percentage after aggregation
               }))

    denom = grouped["within_target"].astype(float) + grouped["outside_target"].astype(float)
    grouped["pct_within_target"] = np.where(denom > 0, grouped["within_target"].astype(float) / denom, np.nan)

    # Create trust-level aggregates (cancer_type IS NULL) for metrics 5 and 8
    # These are pre-computed aggregates that sum across all cancer types for each trust
    # Belt-and-suspenders approach: pipeline creates them AND database validates them
    if metric_val in [5, 8]:
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"Generating trust-level aggregates (cancer_type IS NULL) for metric {metric_val}")

        # Filter to only ALL ROUTES to avoid aggregating across different referral routes
        all_routes_df = grouped[grouped["referral_route"] == "ALL ROUTES"].copy()

        if len(all_routes_df) == 0:
            logger.warning(f"No 'ALL ROUTES' rows found for metric {metric_val}. Cannot create trust aggregates.")
        else:
            # Aggregate by trust (sum across all cancer types)
            trust_agg = (all_routes_df
                        .groupby(["period", "metric", "metric_label", "org_code", "org_name", "referral_route"], as_index=False)
                        .agg({
                            "within_target": "sum",
                            "outside_target": "sum",
                        }))

            # Set cancer_type to empty string to mark these as trust-level aggregates
            # (empty string allows proper unique constraint with ON CONFLICT upserts)
            trust_agg["cancer_type"] = ""

            # Recalculate percentage based on aggregated counts
            agg_denom = trust_agg["within_target"].astype(float) + trust_agg["outside_target"].astype(float)
            trust_agg["pct_within_target"] = np.where(agg_denom > 0,
                                                      trust_agg["within_target"].astype(float) / agg_denom,
                                                      np.nan)

            logger.info(f"Created {len(trust_agg)} trust-level aggregate rows")

            # Validation: compare aggregate with sum of components
            for _, agg_row in trust_agg.iterrows():
                org_code = agg_row["org_code"]
                period = agg_row["period"]

                # Find corresponding disaggregated rows
                components = grouped[
                    (grouped["org_code"] == org_code) &
                    (grouped["period"] == period) &
                    (grouped["referral_route"] == "ALL ROUTES") &
                    (grouped["cancer_type"].notna())  # Exclude the aggregate row itself
                ]

                if len(components) > 0:
                    sum_within = components["within_target"].sum()
                    sum_outside = components["outside_target"].sum()

                    agg_within = agg_row["within_target"]
                    agg_outside = agg_row["outside_target"]

                    # Defensive check: aggregate should equal sum of components
                    if not (np.isclose(sum_within, agg_within) and np.isclose(sum_outside, agg_outside)):
                        logger.error(
                            f"VALIDATION FAILED for {org_code} period {period}: "
                            f"Aggregate ({agg_within}/{agg_outside}) does NOT match "
                            f"sum of components ({sum_within}/{sum_outside})"
                        )
                    else:
                        logger.debug(f"Validation passed for {org_code}: aggregate matches sum of components")

            # Combine disaggregated and aggregated data
            grouped = pd.concat([grouped, trust_agg], ignore_index=True)

            logger.info(f"Final dataset: {len(grouped)} total rows (disaggregated + trust aggregates)")

    return grouped
