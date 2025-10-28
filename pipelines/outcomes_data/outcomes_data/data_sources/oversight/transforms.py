from __future__ import annotations

import logging

import pandas as pd


logger = logging.getLogger(__name__)


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to snake_case and fix common typos.

    Args:
        df: DataFrame with raw column names

    Returns:
        DataFrame with normalized column names
    """
    # Strip whitespace, lowercase, replace spaces with underscores
    # Fix typo: 'colum' -> 'column' (present in source data)
    df.columns = [
        col.strip().lower().replace(' ', '_').replace('colum', 'column')
        for col in df.columns
    ]

    # Fix specific column name issues
    if 'sub-domain' in df.columns:
        df.rename(columns={'sub-domain': 'sub_domain'}, inplace=True)

    # Rename for consistency with database schema
    if 'trust_code' in df.columns:
        df.rename(columns={'trust_code': 'org_code'}, inplace=True)

    return df


def coerce_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Coerce specified columns to numeric, converting invalid values to NaN.

    Args:
        df: DataFrame to process
        columns: List of column names to coerce

    Returns:
        DataFrame with numeric columns coerced
    """
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def trim_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace from all string/object columns.

    Args:
        df: DataFrame to process

    Returns:
        DataFrame with trimmed string columns
    """
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.strip()

    return df


def load_bronze_metrics(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Load and normalize raw metrics data (Bronze layer).

    Args:
        raw_df: Raw DataFrame from combined CSV downloads

    Returns:
        Bronze DataFrame with normalized columns
    """
    if raw_df.empty:
        logger.warning("Empty DataFrame provided to load_bronze_metrics")
        return raw_df

    logger.info(f"Loading bronze metrics: {len(raw_df)} raw rows")

    # Normalize column names
    df = normalize_column_names(raw_df.copy())

    return df


def load_bronze_league_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Load and normalize raw league table data (Bronze layer).

    Args:
        raw_df: Raw DataFrame from combined CSV downloads

    Returns:
        Bronze DataFrame with normalized columns
    """
    if raw_df.empty:
        logger.warning("Empty DataFrame provided to load_bronze_league_table")
        return raw_df

    logger.info(f"Loading bronze league table: {len(raw_df)} raw rows")

    # Normalize column names (includes 'colum' -> 'column' fix)
    df = normalize_column_names(raw_df.copy())

    return df


def clean_metrics_data(bronze_df: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate metrics data (Silver layer).

    Transformations:
    - Coerce numeric columns
    - Trim whitespace from strings
    - Drop rows with missing reporting_date

    Args:
        bronze_df: Bronze DataFrame with normalized columns

    Returns:
        Silver DataFrame ready for database insert
    """
    if bronze_df.empty:
        return bronze_df

    df = bronze_df.copy()

    # Coerce numeric columns
    numeric_cols = ['value', 'median_value', 'lower_quartile', 'upper_quartile', 'rank']
    df = coerce_numeric_columns(df, numeric_cols)

    # Trim whitespace from strings
    df = trim_string_columns(df)

    # Drop rows where essential identifiers are missing
    if 'reporting_date' in df.columns:
        initial_count = len(df)
        df.dropna(subset=['reporting_date'], inplace=True)
        dropped = initial_count - len(df)
        if dropped > 0:
            logger.info(f"Dropped {dropped} rows with null reporting_date")

    logger.info(f"Cleaned metrics data: {len(df)} rows")
    return df


def clean_league_table_data(bronze_df: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate league table data (Silver layer).

    Transformations:
    - Coerce numeric columns
    - Trim whitespace from strings

    Args:
        bronze_df: Bronze DataFrame with normalized columns

    Returns:
        Silver DataFrame ready for database insert
    """
    if bronze_df.empty:
        return bronze_df

    df = bronze_df.copy()

    # Coerce numeric columns
    numeric_cols = ['average_score', 'segment', 'rank']
    df = coerce_numeric_columns(df, numeric_cols)

    # Trim whitespace from strings
    df = trim_string_columns(df)

    logger.info(f"Cleaned league table data: {len(df)} rows")
    return df


def extract_organisations(league_table_df: pd.DataFrame) -> pd.DataFrame:
    """Extract unique organisations from league table data.

    This populates the dim_organisations table with region, trust_type,
    and trust_subtype metadata needed for cohort benchmarking.

    Args:
        league_table_df: Cleaned league table DataFrame

    Returns:
        DataFrame with unique organisations (deduplicated by org_code)
    """
    org_cols = [
        'org_code',
        'trust_name',
        'region',
        'trust_type',
        'trust_subtype',
    ]

    # Check if all required columns are present
    if not all(col in league_table_df.columns for col in org_cols):
        missing = [col for col in org_cols if col not in league_table_df.columns]
        logger.warning(f"Missing organisation columns: {missing}. Cannot extract organisations.")
        return pd.DataFrame(columns=org_cols)

    # Extract organisation columns
    org_df = league_table_df[org_cols].copy()

    # Drop duplicates, keeping last entry for most recent details
    initial_count = len(org_df)
    org_df.drop_duplicates(subset=['org_code'], keep='last', inplace=True)
    logger.info(f"Extracted {len(org_df)} unique organisations (from {initial_count} rows)")

    return org_df
