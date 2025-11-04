"""Pytest configuration and shared fixtures."""
import pytest
import os
from pathlib import Path
from sqlalchemy import create_engine
from validation.test_utils import ReferenceDataLoader, ValueComparator, get_db_connection


@pytest.fixture(scope="session")
def db_engine():
    """
    Provide database connection for all tests.
    
    Uses DATABASE_URL environment variable or constructs from components.
    """
    return get_db_connection()


@pytest.fixture(scope="session")
def reference_loader():
    """Provide reference data loader for all tests."""
    return ReferenceDataLoader()


@pytest.fixture(scope="function")
def value_comparator():
    """
    Provide value comparator with default tolerances.
    
    Tolerances:
    - Percentages: 0.1 percentage points (0.001)
    - Counts: Exact match required
    """
    return ValueComparator(pct_tolerance=0.001)


@pytest.fixture(scope="session")
def test_period():
    """
    Default test period.
    
    Override via environment variable: TEST_PERIOD=2025-09
    """
    return os.getenv('TEST_PERIOD', '2025-08')


@pytest.fixture(scope="session")
def test_org_codes():
    """
    Sample organisation codes for testing.
    
    Override via environment variable: TEST_ORG_CODES=RJ1,RYJ,RA7
    """
    default_codes = ['RJ1', 'RYJ', 'RA7', 'RRK', 'R0A']
    env_codes = os.getenv('TEST_ORG_CODES')
    
    if env_codes:
        return [code.strip() for code in env_codes.split(',')]
    
    return default_codes


@pytest.fixture(scope="session")
def repo_root():
    """Get repository root directory."""
    return Path(__file__).parent.parent.parent.parent


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "layer1: Layer 1 tests - pipeline output validation"
    )
    config.addinivalue_line(
        "markers", "layer2: Layer 2 tests - database aggregation validation"
    )
    config.addinivalue_line(
        "markers", "layer3: Layer 3 tests - tool output validation"
    )
    config.addinivalue_line(
        "markers", "layer4: Layer 4 tests - end-to-end integration"
    )
    config.addinivalue_line(
        "markers", "cancer: Cancer waiting times tests"
    )
    config.addinivalue_line(
        "markers", "rtt: RTT (referral to treatment) tests"
    )
    config.addinivalue_line(
        "markers", "oversight: NHS oversight framework tests"
    )
    config.addinivalue_line(
        "markers", "critical: Critical tests that catch high-priority bugs"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take >5 seconds to run"
    )
