-- Migration: Add trust-level cancer aggregates (across all cancer types)
-- Purpose: Create aggregate rows with cancer_type IS NULL for overall trust performance
-- These aggregates sum across all cancer types to provide the overall trust-level metric

-- Drop and recreate the metric_values_base view with cancer trust aggregates

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
-- Only create rolled-up ALL ROUTES when source doesn't already have it
cancer_rollup AS (
  SELECT
    cu.period,
    cu.metric_id,
    cu.org_code,
    'ALL ROUTES'::TEXT AS referral_route,
    cu.cancer_type,
    cu.rtt_part_type,
    cu.entity_level,
    CASE WHEN SUM(cu.denominator) > 0 THEN SUM(cu.numerator)::NUMERIC / SUM(cu.denominator)::NUMERIC ELSE NULL END AS value,
    SUM(cu.numerator)::NUMERIC AS numerator,
    SUM(cu.denominator)::NUMERIC AS denominator,
    TRUE AS is_rollup,
    'weighted'::TEXT AS rollup_method
  FROM cancer_union cu
  WHERE cu.referral_route IS DISTINCT FROM 'ALL ROUTES'
  GROUP BY cu.period, cu.metric_id, cu.org_code, cu.cancer_type, cu.rtt_part_type, cu.entity_level
  -- Exclude combinations where source already has ALL ROUTES
  HAVING NOT EXISTS (
    SELECT 1 FROM cancer_union src
    WHERE src.period = cu.period
      AND src.metric_id = cu.metric_id
      AND src.org_code = cu.org_code
      AND src.cancer_type = cu.cancer_type
      AND src.referral_route = 'ALL ROUTES'
  )
),
-- NEW: Trust-level aggregates across ALL cancer types
-- For 28-day (metric=3): sum all rows (no ALL ROUTES in source)
-- For 31/62-day (metric=5,8): sum only ALL ROUTES rows (to avoid double-counting)
cancer_trust_aggregate AS (
  -- 28-day: sum all rows
  SELECT
    c.period::TEXT AS period,
    'cancer_28d_pct_within_target'::TEXT AS metric_id,
    c.org_code,
    'ALL ROUTES'::TEXT AS referral_route,
    NULL::TEXT AS cancer_type,
    NULL::TEXT AS rtt_part_type,
    'provider'::TEXT AS entity_level,
    CASE WHEN SUM(c.within_target + c.outside_target) > 0
         THEN SUM(c.within_target)::NUMERIC / SUM(c.within_target + c.outside_target)::NUMERIC
         ELSE NULL END AS value,
    SUM(c.within_target)::NUMERIC AS numerator,
    SUM(c.within_target + c.outside_target)::NUMERIC AS denominator,
    TRUE AS is_rollup,
    'weighted'::TEXT AS rollup_method
  FROM performance_data.cancer_target_metrics c
  WHERE c.metric = 3
  GROUP BY c.period, c.org_code

  UNION ALL

  -- 31-day and 62-day: sum only ALL ROUTES rows
  SELECT
    c.period::TEXT AS period,
    CASE
      WHEN c.metric = 5 THEN 'cancer_31d_pct_within_target'
      WHEN c.metric = 8 THEN 'cancer_62d_pct_within_target'
    END::TEXT AS metric_id,
    c.org_code,
    'ALL ROUTES'::TEXT AS referral_route,
    NULL::TEXT AS cancer_type,
    NULL::TEXT AS rtt_part_type,
    'provider'::TEXT AS entity_level,
    CASE WHEN SUM(c.within_target + c.outside_target) > 0
         THEN SUM(c.within_target)::NUMERIC / SUM(c.within_target + c.outside_target)::NUMERIC
         ELSE NULL END AS value,
    SUM(c.within_target)::NUMERIC AS numerator,
    SUM(c.within_target + c.outside_target)::NUMERIC AS denominator,
    TRUE AS is_rollup,
    'weighted'::TEXT AS rollup_method
  FROM performance_data.cancer_target_metrics c
  WHERE c.metric IN (5, 8)
    AND c.referral_route = 'ALL ROUTES'
  GROUP BY c.period, c.metric, c.org_code
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
  -- Include all source rows (ALL ROUTES are only excluded from rollup via HAVING NOT EXISTS)
  SELECT period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level, value, numerator, denominator, FALSE AS is_rollup, 'source' AS rollup_method FROM cancer_union
  UNION ALL
  SELECT period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level, value, numerator, denominator, is_rollup, rollup_method FROM cancer_rollup
  UNION ALL
  SELECT period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level, value, numerator, denominator, is_rollup, rollup_method FROM cancer_trust_aggregate
  UNION ALL
  SELECT period, metric_id, org_code, referral_route, cancer_type, rtt_part_type, entity_level, value, numerator, denominator, is_rollup, rollup_method FROM cancer_gap_usc_all
  UNION ALL
  SELECT * FROM oversight
) b
JOIN orgs o USING (org_code)
LEFT JOIN performance_data.metric_catalogue mc USING (metric_id);

COMMENT ON VIEW performance_data.metric_values_base IS 'Unified long view across RTT, Cancer, and Oversight with disaggregation, roll-ups (including trust-level cancer aggregates), and USC vs All gaps.';
COMMENT ON COLUMN performance_data.metric_values_base.disagg_key IS 'Canonical key of disaggregation signature used to scope percentile windows.';

-- Refresh the materialized view to pick up the new aggregates
REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;
