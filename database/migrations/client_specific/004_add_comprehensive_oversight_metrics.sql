-- Migration: 004_add_comprehensive_oversight_metrics
-- Purpose: Extend metric_values_base view to include comprehensive oversight metrics from oversight_metrics_raw
-- Dependencies: 002_performance_data_init.sql
-- Idempotent: Yes
--
-- This migration addresses the issue where only 1 oversight metric (average_score) was being exposed
-- in the unified analytics layer. It extends the oversight CTE to include all individual metrics
-- from oversight_metrics_raw, providing comprehensive coverage across 6 NHS Oversight Framework domains:
-- - Access to services
-- - Effectiveness and experience
-- - Finance and productivity
-- - Patient safety
-- - People and workforce
-- - Summary
--
-- Changes:
-- 1. Extends oversight CTE in metric_values_base with UNION ALL to oversight_metrics_raw
-- 2. Auto-populates metric_catalogue with oversight metrics
-- 3. Refreshes insight_metrics_long materialized view

-- =============================================================================
-- SECTION 1: AUTO-POPULATE METRIC CATALOGUE WITH OVERSIGHT METRICS
-- =============================================================================

-- Insert distinct oversight metrics from raw table into catalogue
-- This makes them discoverable in the unified analytics layer
INSERT INTO performance_data.metric_catalogue (
  metric_id,
  metric_label,
  domain,
  unit,
  higher_is_better,
  target_threshold,
  min_denominator,
  disaggregation_dims,
  source_table,
  notes
)
SELECT DISTINCT
  m.metric_id,
  m.metric_description AS metric_label,
  'oversight' AS domain,
  CASE
    WHEN m.units = 'score' THEN 'score'
    WHEN m.units = 'segment' THEN 'segment'
    WHEN m.units = 'percent' THEN 'percentage'
    WHEN m.units IS NULL THEN 'value'
    ELSE LOWER(m.units)
  END AS unit,
  -- Default assumption: higher scores/percentages are better
  -- Segments are inverse (1 is best, 4 is worst) - we'll handle this in a separate metric later
  CASE
    WHEN m.units = 'segment' THEN false  -- Lower segment numbers are better
    ELSE true  -- Higher scores/percentages are better
  END AS higher_is_better,
  NULL::NUMERIC AS target_threshold,  -- No fixed targets for most oversight metrics
  NULL::INTEGER AS min_denominator,   -- Oversight metrics don't have denominators
  ARRAY[]::TEXT[] AS disaggregation_dims,  -- No disaggregation for oversight
  'performance_data.oversight_metrics_raw' AS source_table,
  CONCAT(
    'Domain: ', COALESCE(m.domain, 'Unknown'),
    ' | Sub-domain: ', COALESCE(m.sub_domain, 'Unknown'),
    ' | Includes national benchmarks (median, Q1, Q3)'
  ) AS notes
FROM performance_data.oversight_metrics_raw m
WHERE m.metric_id NOT IN (
  SELECT metric_id FROM performance_data.metric_catalogue WHERE domain = 'oversight'
)
ON CONFLICT (metric_id) DO NOTHING;

-- Log how many metrics were added
DO $$
DECLARE
  new_metrics_count INTEGER;
BEGIN
  SELECT COUNT(DISTINCT metric_id) INTO new_metrics_count
  FROM performance_data.oversight_metrics_raw;

  RAISE NOTICE 'Added % oversight metrics to catalogue', new_metrics_count;
END $$;

-- =============================================================================
-- SECTION 2: EXTEND metric_values_base VIEW WITH COMPREHENSIVE OVERSIGHT DATA
-- =============================================================================

CREATE OR REPLACE VIEW performance_data.metric_values_base AS
WITH orgs AS (
  SELECT org_code, trust_name AS org_name, region, trust_type, trust_subtype
  FROM performance_data.dim_organisations
),
rtt AS (
  -- Stock metrics from rtt_trust_snapshot_v (provider level)
  SELECT
    s.period,
    'rtt_pct_within_18'::TEXT AS metric_id,
    s.org_code,
    NULL::TEXT AS referral_route,
    NULL::TEXT AS cancer_type,
    s.rtt_part_type,
    s.entity_level,
    s.pct_within_18::NUMERIC AS value,
    NULL::NUMERIC AS numerator,
    s.waiting_list_total::NUMERIC AS denominator,
    FALSE AS is_rollup,
    'source'::TEXT AS rollup_method
  FROM performance_data.rtt_trust_snapshot_v s
  WHERE s.entity_level = 'provider'
  UNION ALL
  SELECT
    s.period,
    'rtt_pct_over_52',
    s.org_code,
    NULL, NULL,
    s.rtt_part_type,
    s.entity_level,
    CASE WHEN s.waiting_list_total > 0 THEN (s.over_52::NUMERIC / NULLIF(s.waiting_list_total::NUMERIC,0)) ELSE NULL END AS value,
    s.over_52::NUMERIC,
    s.waiting_list_total::NUMERIC AS denominator,
    FALSE,
    'source'
  FROM performance_data.rtt_trust_snapshot_v s
  WHERE s.entity_level = 'provider'
  UNION ALL
  SELECT
    s.period,
    'rtt_p92_weeks_waiting',
    s.org_code,
    NULL, NULL,
    s.rtt_part_type,
    s.entity_level,
    s.p92_weeks_waiting::NUMERIC,
    NULL::NUMERIC,
    s.waiting_list_total::NUMERIC,
    FALSE,
    'source'
  FROM performance_data.rtt_trust_snapshot_v s
  WHERE s.entity_level = 'provider'
  UNION ALL
  SELECT
    s.period,
    'rtt_compliance_18w',
    s.org_code,
    NULL, NULL,
    s.rtt_part_type,
    s.entity_level,
    s.compliance_18w::NUMERIC,
    s.completed_within_18::NUMERIC,
    s.completed_total::NUMERIC,
    FALSE,
    'source'
  FROM performance_data.rtt_trust_snapshot_v s
  WHERE s.entity_level = 'provider'
  UNION ALL
  SELECT
    s.period,
    'rtt_unknown_clock_start_rate',
    s.org_code,
    NULL, NULL,
    s.rtt_part_type,
    s.entity_level,
    CASE WHEN (s.waiting_list_total + s.unknown_clock_start) > 0
         THEN (s.unknown_clock_start::NUMERIC / NULLIF((s.waiting_list_total + s.unknown_clock_start)::NUMERIC,0))
         ELSE NULL END,
    s.unknown_clock_start::NUMERIC AS numerator,
    (s.waiting_list_total + s.unknown_clock_start)::NUMERIC AS denominator,
    FALSE,
    'derived'
  FROM performance_data.rtt_trust_snapshot_v s
  WHERE s.entity_level = 'provider'
),
-- Cancer base: select directly by metric code to avoid label variations
-- 28-day (metric=3)
cancer_28 AS (
  SELECT
    c.period::TEXT AS period,
    'cancer_28d_pct_within_target'::TEXT AS metric_id,
    c.org_code,
    c.referral_route,
    c.cancer_type,
    NULL::TEXT AS rtt_part_type,
    'provider'::TEXT AS entity_level,
    c.pct_within_target::NUMERIC AS value,
    c.within_target::NUMERIC AS numerator,
    (c.within_target + c.outside_target)::NUMERIC AS denominator
  FROM performance_data.cancer_target_metrics c
  WHERE c.metric = 3 AND c.referral_route IS NOT NULL
),
-- 31-day (metric=5)
cancer_31 AS (
  SELECT
    c.period::TEXT AS period,
    'cancer_31d_pct_within_target'::TEXT AS metric_id,
    c.org_code,
    c.referral_route,
    c.cancer_type,
    NULL::TEXT AS rtt_part_type,
    'provider'::TEXT AS entity_level,
    c.pct_within_target::NUMERIC AS value,
    c.within_target::NUMERIC AS numerator,
    (c.within_target + c.outside_target)::NUMERIC AS denominator
  FROM performance_data.cancer_target_metrics c
  WHERE c.metric = 5 AND c.referral_route IS NOT NULL
),
-- 62-day (metric=8)
cancer_62 AS (
  SELECT
    c.period::TEXT AS period,
    'cancer_62d_pct_within_target'::TEXT AS metric_id,
    c.org_code,
    c.referral_route,
    c.cancer_type,
    NULL::TEXT AS rtt_part_type,
    'provider'::TEXT AS entity_level,
    c.pct_within_target::NUMERIC AS value,
    c.within_target::NUMERIC AS numerator,
    (c.within_target + c.outside_target)::NUMERIC AS denominator
  FROM performance_data.cancer_target_metrics c
  WHERE c.metric = 8 AND c.referral_route IS NOT NULL
),
cancer_union AS (
  SELECT * FROM cancer_28
  UNION ALL SELECT * FROM cancer_31
  UNION ALL SELECT * FROM cancer_62
),
-- ALL ROUTES roll-up per cancer_type by weighted numerator/denominator when needed
cancer_rollup AS (
  SELECT
    period,
    metric_id,
    org_code,
    'ALL ROUTES'::TEXT AS referral_route,
    cancer_type,
    rtt_part_type,
    entity_level,
    CASE WHEN SUM(denominator) > 0 THEN SUM(numerator)::NUMERIC / SUM(denominator)::NUMERIC ELSE NULL END AS value,
    SUM(numerator)::NUMERIC AS numerator,
    SUM(denominator)::NUMERIC AS denominator,
    TRUE AS is_rollup,
    'weighted'::TEXT AS rollup_method
  FROM cancer_union
  WHERE referral_route IS DISTINCT FROM 'ALL ROUTES'
  GROUP BY period, metric_id, org_code, cancer_type, rtt_part_type, entity_level
),
-- USC vs ALL gap (derived metric rows)
cancer_gap_usc_all AS (
  SELECT
    cr.period,
    CASE
      WHEN cr.metric_id = 'cancer_28d_pct_within_target' THEN 'cancer_28d_gap_usc_all'
      WHEN cr.metric_id = 'cancer_31d_pct_within_target' THEN 'cancer_31d_gap_usc_all'
      WHEN cr.metric_id = 'cancer_62d_pct_within_target' THEN 'cancer_62d_gap_usc_all'
    END AS metric_id,
    cr.org_code,
    'GAP'::TEXT AS referral_route,
    cr.cancer_type,
    NULL::TEXT AS rtt_part_type,
    cr.entity_level,
    (usc.value - ar.value) AS value,
    NULL::NUMERIC AS numerator,
    NULL::NUMERIC AS denominator,
    TRUE AS is_rollup,
    'derived_gap'::TEXT AS rollup_method
  FROM (
    SELECT
      period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level,
      value, numerator, denominator, FALSE AS is_rollup, 'source'::TEXT AS rollup_method
    FROM cancer_union WHERE referral_route = 'ALL ROUTES'
    UNION ALL
    SELECT
      period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level,
      value, numerator, denominator, is_rollup, rollup_method
    FROM cancer_rollup
  ) ar
  JOIN cancer_union usc
    ON usc.period = ar.period
   AND usc.metric_id = ar.metric_id
   AND usc.org_code = ar.org_code
   AND usc.cancer_type = ar.cancer_type
   AND usc.referral_route = 'URGENT SUSPECTED CANCER'
  JOIN cancer_union cr
    ON cr.period = ar.period AND cr.metric_id = ar.metric_id AND cr.org_code = ar.org_code AND cr.cancer_type = ar.cancer_type AND cr.referral_route = 'ALL ROUTES'
),
oversight AS (
  -- ORIGINAL: League table average score
  SELECT
    o.reporting_date::TEXT AS period,
    'oversight_average_score'::TEXT AS metric_id,
    o.org_code,
    NULL::TEXT AS referral_route,
    NULL::TEXT AS cancer_type,
    NULL::TEXT AS rtt_part_type,
    'provider'::TEXT AS entity_level,
    o.average_score::NUMERIC AS value,
    NULL::NUMERIC AS numerator,
    NULL::NUMERIC AS denominator,
    FALSE AS is_rollup,
    'source'::TEXT AS rollup_method
  FROM performance_data.oversight_league_table_raw o

  UNION ALL

  -- NEW: All individual oversight metrics from raw table
  -- This adds comprehensive coverage across 6 domains with 20+ distinct metrics
  SELECT
    m.reporting_date::TEXT AS period,
    m.metric_id::TEXT AS metric_id,
    m.org_code,
    NULL::TEXT AS referral_route,
    NULL::TEXT AS cancer_type,
    NULL::TEXT AS rtt_part_type,
    'provider'::TEXT AS entity_level,
    m.value::NUMERIC AS value,
    NULL::NUMERIC AS numerator,
    NULL::NUMERIC AS denominator,
    FALSE AS is_rollup,
    'source'::TEXT AS rollup_method
  FROM performance_data.oversight_metrics_raw m
  WHERE m.metric_id IS NOT NULL  -- Ensure we have valid metric IDs
    AND m.value IS NOT NULL       -- Only include rows with actual values
)
SELECT
  b.period,
  b.metric_id,
  mc.metric_label,
  mc.domain,
  o.org_code,
  o.org_name,
  o.region,
  o.trust_type,
  o.trust_subtype,
  b.referral_route,
  b.cancer_type,
  b.rtt_part_type,
  b.entity_level,
  b.value,
  mc.unit,
  b.numerator,
  b.denominator,
  CASE
    WHEN b.denominator IS NOT NULL AND mc.min_denominator IS NOT NULL THEN (b.denominator >= mc.min_denominator)
    WHEN b.denominator IS NULL THEN TRUE
    ELSE TRUE
  END AS valid_sample,
  mc.target_threshold,
  CASE WHEN mc.target_threshold IS NOT NULL AND b.value IS NOT NULL
       THEN (CASE WHEN mc.higher_is_better THEN b.value >= mc.target_threshold ELSE b.value <= mc.target_threshold END)
       ELSE NULL END AS target_met,
  mc.higher_is_better,
  b.is_rollup,
  b.rollup_method,
  concat_ws(' | ', coalesce(b.referral_route,'~'), coalesce(b.cancer_type,'~'), coalesce(b.rtt_part_type,'~'), coalesce(b.entity_level,'~')) AS disagg_key
FROM (
  SELECT * FROM rtt
  UNION ALL
  SELECT period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level, value, numerator, denominator, FALSE AS is_rollup, 'source' AS rollup_method FROM cancer_union
  UNION ALL
  SELECT period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level, value, numerator, denominator, is_rollup, rollup_method FROM cancer_rollup
  UNION ALL
  SELECT period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level, value, numerator, denominator, is_rollup, rollup_method FROM cancer_gap_usc_all
  UNION ALL
  SELECT * FROM oversight
) b
JOIN orgs o USING (org_code)
LEFT JOIN performance_data.metric_catalogue mc USING (metric_id);

COMMENT ON VIEW performance_data.metric_values_base IS 'Unified long view across RTT, Cancer, and Oversight (now comprehensive) with disaggregation, roll-ups, and USC vs All gaps.';

-- =============================================================================
-- SECTION 3: REFRESH MATERIALIZED VIEW TO APPLY CHANGES
-- =============================================================================

-- Refresh the materialized view to include the new oversight metrics
REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;

-- Log completion
DO $$
DECLARE
  oversight_count INTEGER;
  rj1_oversight_count INTEGER;
BEGIN
  -- Count total oversight metrics in materialized view
  SELECT COUNT(DISTINCT metric_id) INTO oversight_count
  FROM performance_data.insight_metrics_long
  WHERE domain = 'oversight';

  -- Count oversight metrics for a specific trust (RJ1 - Guy's and St Thomas')
  SELECT COUNT(DISTINCT metric_id) INTO rj1_oversight_count
  FROM performance_data.insight_metrics_long
  WHERE domain = 'oversight' AND org_code = 'RJ1';

  RAISE NOTICE 'Migration complete: % total oversight metrics defined, RJ1 has % metrics',
    oversight_count, rj1_oversight_count;
END $$;
