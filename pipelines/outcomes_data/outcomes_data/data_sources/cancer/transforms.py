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
    """Flatten multi-level headers and clean column names, ensuring uniqueness."""
    new_cols = []
    col_counts = {}
    for col in df.columns:
        level1 = str(col[0]) if pd.notna(col[0]) else ''
        level2 = str(col[1]) if pd.notna(col[1]) else ''

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

    df = _clean_column_names(bronze_df.copy())
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
    route_col = first_existing(["referral_route"])  # optional
    treatment_stage_col = first_existing(["treatment_stage", "stageroute", "stage_route"])  # for 31-day combined data

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

    # Keep all referral routes to provide breakdown (including 'ALL ROUTES' rows if present)

    # Filter for metric 5 (31-day): only keep "First Treatment" rows to avoid double-counting
    # The CSV contains separate rows for "First Treatment" and "Subsequent Treatment"
    # Per NHS England guidance, the 31-day standard reports ONLY "First Treatment"
    # Summing First + Subsequent would incorrectly double-count and inflate volumes
    if metric_val == 5 and treatment_stage_col and treatment_stage_col in df.columns:
        df = df[df[treatment_stage_col].str.upper().str.strip() == "FIRST TREATMENT"].copy()

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

    minimal = pd.DataFrame({
        "period": df["period"],
        "metric": df["metric"],
        "metric_label": metric_label,
        "org_code": df[org_code_col],
        "org_name": df[org_name_col],
        "cancer_type": df[cancer_type_col],
        "referral_route": df[route_col] if route_col else "ALL ROUTES",
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

    return grouped
