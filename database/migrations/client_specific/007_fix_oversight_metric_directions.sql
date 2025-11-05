-- Migration: Fix higher_is_better flags for oversight metrics
-- Purpose: Correct the direction flags for metrics where lower values indicate better performance
-- Dependencies: 004_add_comprehensive_oversight_metrics.sql
-- Idempotent: Yes
--
-- Background:
-- Migration 004 auto-populated oversight metrics with a blanket assumption that higher_is_better=true
-- for all non-segment metrics. This is incorrect for many metrics where lower values are better
-- (e.g., infection rates, waiting times, adverse events, costs, etc.)
--
-- This causes percentile calculations to be inverted, making poor performers appear as top performers.

-- =============================================================================
-- SECTION 1: FIX METRIC CATALOGUE DIRECTION FLAGS
-- =============================================================================

-- Update metrics where LOWER values indicate BETTER performance
UPDATE performance_data.metric_catalogue
SET higher_is_better = false
WHERE metric_id IN (
  -- Waiting time metrics (lower wait = better)
  'OF0003',  -- % waiting over 52 weeks for elective
  'OF0005',  -- % waiting over 52 weeks for community services
  'OF0014',  -- % spending >12 hours in A&E
  'OF0017',  -- Average Category 2 ambulance response time
  'OF0025',  -- Average days from discharge-ready to discharge
  'OF0063',  -- % inpatients with >60 day length of stay

  -- Infection/safety metrics (lower rate/count = better)
  'OF0020',  -- Number of MRSA infections
  'OF0048',  -- Rate of E-Coli infections
  'OF0088',  -- Rate of C-Difficile infections

  -- Workforce metrics (lower = better)
  'OF0082',  -- Sickness absence rate

  -- Cost metrics (lower cost = better)
  'OF0086',  -- Relative difference in costs

  -- Normalized score versions (OF1xxx series) - same metrics as above
  'OF1003',  -- Score: % waiting over 52 weeks for elective
  'OF1005',  -- Score: % waiting over 52 weeks for community
  'OF1014',  -- Score: % spending >12 hours in A&E
  'OF1017',  -- Score: Average Category 2 ambulance response time
  'OF1020',  -- Score: Number of MRSA infections
  'OF1025',  -- Score: Average days from discharge-ready to discharge
  'OF1048',  -- Score: Rate of E-Coli infections
  'OF1063',  -- Score: % inpatients with >60 day LOS
  'OF1082',  -- Score: Sickness absence rate
  'OF1086',  -- Score: Relative difference in costs
  'OF1088'   -- Score: Rate of C-Difficile infections
)
AND domain = 'oversight';

-- Log the changes
DO $$
DECLARE
  updated_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO updated_count
  FROM performance_data.metric_catalogue
  WHERE higher_is_better = false AND domain = 'oversight';

  RAISE NOTICE 'Updated metric catalogue: % oversight metrics now marked as "lower is better"', updated_count;
END $$;

-- =============================================================================
-- SECTION 2: REFRESH MATERIALIZED VIEW TO APPLY CORRECTIONS
-- =============================================================================

-- The materialized view uses the metric_catalogue's higher_is_better flag,
-- and now applies inversion to percentiles for "lower is better" metrics.
-- Refreshing will recalculate all percentiles with corrected direction.

REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;

-- Log completion with sample verification
DO $$
DECLARE
  rvv_of0014_percentile NUMERIC;
  rvv_of0014_value NUMERIC;
BEGIN
  -- Verify fix for RVV (East Kent Hospitals) OF0014 metric
  SELECT percentile_overall, value
  INTO rvv_of0014_percentile, rvv_of0014_value
  FROM performance_data.insight_metrics_long
  WHERE org_code = 'RVV' AND metric_id = 'OF0014'
  LIMIT 1;

  IF rvv_of0014_percentile IS NOT NULL THEN
    RAISE NOTICE 'Verification: RVV OF0014 (12-hr A&E waits) = %.1f%% @ %.1f percentile (should be low percentile for poor performance)',
      rvv_of0014_value, rvv_of0014_percentile * 100;
  END IF;

  RAISE NOTICE 'Migration 007 complete: Percentile calculations now correctly inverted for "lower is better" metrics';
END $$;
