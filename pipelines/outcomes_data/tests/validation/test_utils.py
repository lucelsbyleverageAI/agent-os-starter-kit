"""Utilities for validation testing."""
import os
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from sqlalchemy import create_engine, Engine


class ReferenceDataLoader:
    """Load NHS published spreadsheets as reference data."""

    def __init__(self, spreadsheets_dir: Optional[str] = None):
        """
        Initialize reference data loader.
        
        Args:
            spreadsheets_dir: Path to public_aggregated_spreadsheets directory.
                            If None, uses default path relative to this file.
        """
        if spreadsheets_dir is None:
            # Default: pipelines/outcomes_data/outcomes_data/public_aggregated_spreadsheets
            test_dir = Path(__file__).parent.parent.parent
            spreadsheets_dir = test_dir / "outcomes_data" / "public_aggregated_spreadsheets"
        
        self.spreadsheets_dir = Path(spreadsheets_dir)
        
        if not self.spreadsheets_dir.exists():
            raise FileNotFoundError(
                f"Reference spreadsheets directory not found: {self.spreadsheets_dir}"
            )

    def load_cancer_reference(self, period: str) -> pd.DataFrame:
        """
        Load cancer reference data for a specific period.
        
        Args:
            period: Period in YYYY-MM format (e.g., '2025-08')
            
        Returns:
            DataFrame with standardized column names
        """
        csv_path = self.spreadsheets_dir / "cancer" / "Monthly-CSV.csv"
        
        if not csv_path.exists():
            raise FileNotFoundError(f"Cancer reference file not found: {csv_path}")
        
        df = pd.read_csv(csv_path)
        
        # Parse period format (DD/MM/YYYY → YYYY-MM)
        if '/' in str(df['Period'].iloc[0]):
            df['period_parsed'] = pd.to_datetime(
                df['Period'], format='%d/%m/%Y'
            ).dt.strftime('%Y-%m')
        else:
            df['period_parsed'] = df['Period']
        
        # Filter to requested period
        df = df[df['period_parsed'] == period].copy()
        
        return df

    def load_rtt_reference(self, period: str) -> pd.DataFrame:
        """
        Load RTT reference data for a specific period.
        
        Args:
            period: Period in YYYY-MM format (e.g., '2025-08')
            
        Returns:
            DataFrame with standardized column names
        """
        # Find RTT file (pattern: *RTT*.csv)
        rtt_dir = self.spreadsheets_dir / "rtt"
        
        if not rtt_dir.exists():
            raise FileNotFoundError(f"RTT directory not found: {rtt_dir}")
        
        rtt_files = list(rtt_dir.glob("*RTT*.csv"))
        
        if not rtt_files:
            raise FileNotFoundError(f"No RTT files found in: {rtt_dir}")
        
        # Use most recent file (sorted by name)
        csv_path = sorted(rtt_files)[-1]
        
        df = pd.read_csv(csv_path)
        
        # Parse period (assuming similar format to cancer)
        # RTT files may have different formats - adjust as needed
        
        return df

    def load_oversight_reference(self, trust_type: str = "acute") -> pd.DataFrame:
        """
        Load oversight framework reference data.
        
        Args:
            trust_type: Type of trust ('acute', 'ambulance', 'non-acute')
            
        Returns:
            DataFrame with standardized column names
        """
        oversight_dir = self.spreadsheets_dir / "oversight"
        
        if not oversight_dir.exists():
            raise FileNotFoundError(f"Oversight directory not found: {oversight_dir}")
        
        # Map trust type to file name
        file_map = {
            "acute": "nhs-oversight-framework-acute-trust-data.csv",
            "ambulance": "nhs-oversight-framework-ambulance-trust-data.csv",
            "non-acute": "nhs-oversight-framework-non-acute-hospital-trust-data.csv"
        }
        
        if trust_type not in file_map:
            raise ValueError(f"Invalid trust_type: {trust_type}. Must be one of {list(file_map.keys())}")
        
        csv_path = oversight_dir / file_map[trust_type]
        
        if not csv_path.exists():
            raise FileNotFoundError(f"Oversight file not found: {csv_path}")
        
        df = pd.read_csv(csv_path)
        
        return df


class ValueComparator:
    """Compare numeric values with tolerance handling."""

    def __init__(self, rtol: float = 1e-5, atol: float = 1e-8, pct_tolerance: float = 0.001):
        """
        Initialize value comparator.
        
        Args:
            rtol: Relative tolerance for floating point comparison
            atol: Absolute tolerance for floating point comparison
            pct_tolerance: Tolerance for percentage comparison (default: 0.001 = 0.1 percentage points)
        """
        self.rtol = rtol
        self.atol = atol
        self.pct_tolerance = pct_tolerance

    def compare_percentages(self, val1: float, val2: float) -> Tuple[bool, float]:
        """
        Compare two percentage values.
        
        Args:
            val1: First percentage (as decimal: 0.907 = 90.7%)
            val2: Second percentage (as decimal)
            
        Returns:
            Tuple of (is_match, absolute_difference)
        """
        diff = abs(val1 - val2)
        matches = diff <= self.pct_tolerance
        return matches, diff

    def compare_counts(self, val1: int, val2: int) -> Tuple[bool, int]:
        """
        Compare two count values (must be exact).
        
        Args:
            val1: First count
            val2: Second count
            
        Returns:
            Tuple of (is_match, absolute_difference)
        """
        diff = abs(int(val1) - int(val2))
        matches = diff == 0
        return matches, diff

    def compare_floats(self, val1: float, val2: float) -> Tuple[bool, float]:
        """
        Compare two floating point values with relative/absolute tolerance.
        
        Args:
            val1: First value
            val2: Second value
            
        Returns:
            Tuple of (is_match, absolute_difference)
        """
        diff = abs(val1 - val2)
        # Check both relative and absolute tolerance
        rel_check = diff <= abs(val1) * self.rtol
        abs_check = diff <= self.atol
        matches = rel_check or abs_check
        return matches, diff


def get_db_connection() -> Engine:
    """
    Get database connection from environment.
    
    Returns:
        SQLAlchemy engine
        
    Environment Variables:
        DATABASE_URL: Full database URL (priority)
        POSTGRES_PASSWORD: Password if using default connection
    """
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        # Construct from individual components
        password = os.getenv('POSTGRES_PASSWORD', 'postgres')
        host = os.getenv('POSTGRES_HOST', 'localhost')
        port = os.getenv('POSTGRES_PORT', '5432')
        user = os.getenv('POSTGRES_USER', 'postgres')
        db = os.getenv('POSTGRES_DB', 'postgres')
        
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    return create_engine(db_url)


def format_comparison_result(
    org_code: str,
    metric_name: str,
    ref_value: float,
    db_value: float,
    ref_numerator: Optional[int] = None,
    db_numerator: Optional[int] = None,
    ref_denominator: Optional[int] = None,
    db_denominator: Optional[int] = None
) -> Dict:
    """
    Format comparison result for reporting.
    
    Args:
        org_code: Organisation code
        metric_name: Name of metric being compared
        ref_value: Reference value from spreadsheet
        db_value: Database value
        ref_numerator: Reference numerator (optional)
        db_numerator: Database numerator (optional)
        ref_denominator: Reference denominator (optional)
        db_denominator: Database denominator (optional)
        
    Returns:
        Dictionary with formatted comparison details
    """
    result = {
        'org_code': org_code,
        'metric_name': metric_name,
        'ref_value': f"{ref_value:.1%}" if ref_value < 1.5 else f"{ref_value}",
        'db_value': f"{db_value:.1%}" if db_value < 1.5 else f"{db_value}",
        'diff': f"{abs(ref_value - db_value):.3%}" if ref_value < 1.5 else f"{abs(ref_value - db_value):.2f}",
    }
    
    if ref_numerator is not None and db_numerator is not None:
        result['ref_numerator'] = int(ref_numerator)
        result['db_numerator'] = int(db_numerator)
        result['numerator_diff'] = int(abs(ref_numerator - db_numerator))
    
    if ref_denominator is not None and db_denominator is not None:
        result['ref_denominator'] = int(ref_denominator)
        result['db_denominator'] = int(db_denominator)
        result['denominator_diff'] = int(abs(ref_denominator - db_denominator))
    
    return result
