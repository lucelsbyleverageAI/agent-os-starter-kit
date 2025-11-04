#!/bin/bash
# Run NHS outcomes data validation tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================================"
echo "NHS Outcomes Data Validation Test Suite"
echo "================================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Must run from pipelines/outcomes_data directory${NC}"
    exit 1
fi

# Check for test results directory
mkdir -p test_results

# Set database connection if not already set
if [ -z "$DATABASE_URL" ]; then
    if [ -z "$POSTGRES_PASSWORD" ]; then
        echo -e "${YELLOW}Warning: POSTGRES_PASSWORD not set, using default 'postgres'${NC}"
        export POSTGRES_PASSWORD="postgres"
    fi
    export DATABASE_URL="postgresql://postgres:${POSTGRES_PASSWORD}@localhost:5432/postgres"
    echo "Using database: localhost:5432"
fi

# Parse command line arguments
RUN_MODE="all"
TEST_MARKERS=""
VERBOSE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --critical)
            RUN_MODE="critical"
            TEST_MARKERS="-m critical"
            shift
            ;;
        --cancer)
            RUN_MODE="cancer"
            TEST_MARKERS="-m cancer"
            shift
            ;;
        --layer1)
            RUN_MODE="layer1"
            TEST_MARKERS="-m layer1"
            shift
            ;;
        --verbose|-v)
            VERBOSE="-vv"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --critical    Run only critical tests"
            echo "  --cancer      Run only cancer tests"
            echo "  --layer1      Run only Layer 1 (pipeline output) tests"
            echo "  --verbose, -v Run with verbose output"
            echo "  --help, -h    Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  DATABASE_URL       Database connection string"
            echo "  POSTGRES_PASSWORD  Database password (if DATABASE_URL not set)"
            echo "  TEST_PERIOD        Test period in YYYY-MM format (default: 2025-08)"
            echo "  TEST_ORG_CODES     Comma-separated org codes to test"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Run with --help for usage information"
            exit 1
            ;;
    esac
done

# Display test configuration
echo "Test Configuration:"
echo "  Mode: $RUN_MODE"
echo "  Period: ${TEST_PERIOD:-2025-08 (default)}"
if [ -n "$TEST_ORG_CODES" ]; then
    echo "  Org Codes: $TEST_ORG_CODES"
fi
echo ""

# Check if poetry is available
if ! command -v poetry &> /dev/null; then
    echo -e "${RED}Error: poetry not found. Please install poetry first.${NC}"
    exit 1
fi

# Run tests
echo "Running tests..."
echo ""

if poetry run pytest tests/validation/ \
    $TEST_MARKERS \
    $VERBOSE \
    --tb=short \
    --html=test_results/validation_report.html \
    --self-contained-html \
    2>&1 | tee test_results/test_output.log; then
    
    echo ""
    echo "================================================================"
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo "================================================================"
    echo ""
    echo "Test report: test_results/validation_report.html"
    echo "Test log:    test_results/test_output.log"
    echo ""
    exit 0
else
    echo ""
    echo "================================================================"
    echo -e "${RED}✗ Some tests failed${NC}"
    echo "================================================================"
    echo ""
    echo "Test report: test_results/validation_report.html"
    echo "Test log:    test_results/test_output.log"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check test_results/validation_report.html for details"
    echo "  2. Review NHS_DEBUGGING_GUIDE.md for diagnostic queries"
    echo "  3. Verify database connection: psql \$DATABASE_URL -c 'SELECT 1'"
    echo "  4. Check if data is loaded for test period: $TEST_PERIOD"
    echo ""
    exit 1
fi
