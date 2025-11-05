-- Migration: 002_performance_data_init
-- Purpose: Comprehensive initialization of performance_data schema with all tables, views, and seed data
-- Dependencies: None (self-contained)
-- Idempotent: Yes
--
-- This migration creates a complete, isolated performance_data schema for NHS outcomes data pipeline:
-- - 6 core tables (RTT, Cancer, Oversight, Organisations, Metric Catalogue)
-- - 3 views in performance_data schema
-- - 1 materialized view with indexes for benchmarking
-- - 3 public schema views for PostgREST API access
-- - Seed data for metric catalogue (10 metrics)
-- - Grants for API access

-- =============================================================================
-- SECTION 1: SCHEMA & CORE TABLES
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS performance_data;

COMMENT ON SCHEMA performance_data IS 'Analytics schema for NHS performance datasets and marts.';

-- -----------------------------------------------------------------------------
-- Table: metric_catalogue
-- Purpose: Defines metric semantics, targets, and disaggregation dimensions
-- Source: Migration 002
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS performance_data.metric_catalogue (
    metric_id TEXT PRIMARY KEY,
    metric_label TEXT NOT NULL,
    domain TEXT NOT NULL CHECK (domain IN ('rtt','cancer','oversight')),
    unit TEXT NOT NULL,                                -- e.g. 'percentage','weeks','count','score'
    higher_is_better BOOLEAN NOT NULL,
    target_threshold NUMERIC,                          -- optional threshold for target_met evaluation
    min_denominator INTEGER DEFAULT 20,                -- sample size floor for valid_sample
    disaggregation_dims TEXT[] DEFAULT '{}',           -- e.g. '{referral_route,cancer_type}'
    source_table TEXT NOT NULL,
    notes TEXT
);

COMMENT ON TABLE performance_data.metric_catalogue IS 'Defines metric semantics (direction, units, targets), stability rules, and disaggregation for benchmarking.';
COMMENT ON COLUMN performance_data.metric_catalogue.metric_id IS 'Stable identifier for a metric or derived signal (e.g., rtt_pct_within_18, cancer_62d_pct_within_target).';
COMMENT ON COLUMN performance_data.metric_catalogue.metric_label IS 'Human-readable label for display.';
COMMENT ON COLUMN performance_data.metric_catalogue.domain IS 'Dataset family the metric belongs to: rtt | cancer | oversight.';
COMMENT ON COLUMN performance_data.metric_catalogue.unit IS 'Unit of measure for value (percentage, weeks, count, score).';
COMMENT ON COLUMN performance_data.metric_catalogue.higher_is_better IS 'Whether higher values indicate better performance; used to orient rankings and scores.';
COMMENT ON COLUMN performance_data.metric_catalogue.target_threshold IS 'Optional threshold defining target attainment for this metric and period (if applicable).';
COMMENT ON COLUMN performance_data.metric_catalogue.min_denominator IS 'Sample-size floor for valid_sample; rows under this are excluded from percentile windows.';
COMMENT ON COLUMN performance_data.metric_catalogue.disaggregation_dims IS 'Declared disaggregation dimensions for this metric (e.g., referral_route, cancer_type, rtt_part_type).';
COMMENT ON COLUMN performance_data.metric_catalogue.source_table IS 'Primary source table/view where the metric originates (for auditability).';
COMMENT ON COLUMN performance_data.metric_catalogue.notes IS 'Free-text notes about metric construction or caveats.';

-- -----------------------------------------------------------------------------
-- Table: rtt_metrics_gold
-- Purpose: RTT (Referral to Treatment) waiting times gold layer metrics
-- Source: database.py CREATE_GOLD_SQL
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS performance_data.rtt_metrics_gold (
  period TEXT NOT NULL,
  entity_level TEXT NOT NULL,
  org_code TEXT NOT NULL,
  org_name TEXT,
  rtt_part_type TEXT,
  completed_total NUMERIC,
  completed_within_18 NUMERIC,
  incomplete_total NUMERIC,
  over_18 NUMERIC,
  over_26 NUMERIC,
  over_40 NUMERIC,
  over_52 NUMERIC,
  over_65 NUMERIC,
  over_78 NUMERIC,
  unknown_clock_start NUMERIC,
  compliance_18w DOUBLE PRECISION,
  waiting_list_total NUMERIC,
  pct_over_18 DOUBLE PRECISION,
  pct_over_26 DOUBLE PRECISION,
  pct_over_40 DOUBLE PRECISION,
  pct_over_52 DOUBLE PRECISION,
  pct_over_65 DOUBLE PRECISION,
  pct_over_78 DOUBLE PRECISION,
  median_weeks_completed DOUBLE PRECISION,
  p95_weeks_completed DOUBLE PRECISION,
  median_weeks_waiting DOUBLE PRECISION,
  p92_weeks_waiting DOUBLE PRECISION,
  PRIMARY KEY (period, entity_level, org_code, rtt_part_type)
);

COMMENT ON TABLE performance_data.rtt_metrics_gold IS 'RTT waiting times gold metrics with compliance, waiting list stats, and quantiles.';

-- -----------------------------------------------------------------------------
-- Table: cancer_target_metrics
-- Purpose: Cancer waiting times target performance (28-day, 31-day, 62-day standards)
-- Source: cancer/writer_postgres.py upsert_target_gold
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS performance_data.cancer_target_metrics (
  period VARCHAR NOT NULL,
  metric BIGINT NOT NULL,
  metric_label VARCHAR,
  org_code VARCHAR NOT NULL,
  org_name VARCHAR,
  cancer_type VARCHAR NOT NULL,
  referral_route VARCHAR NOT NULL DEFAULT 'ALL ROUTES',
  within_target NUMERIC,
  outside_target NUMERIC,
  pct_within_target DOUBLE PRECISION,
  PRIMARY KEY (period, metric, org_code, cancer_type, referral_route)
);

COMMENT ON TABLE performance_data.cancer_target_metrics IS 'Cancer waiting times performance against NHS targets (metrics 3, 5, 8).';

-- -----------------------------------------------------------------------------
-- Table: oversight_metrics_raw
-- Purpose: NHS Oversight Framework detailed metrics by domain
-- Source: database.py CREATE_OVERSIGHT_METRICS_SQL
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS performance_data.oversight_metrics_raw (
    region TEXT,
    trust_type TEXT,
    trust_subtype TEXT,
    org_code TEXT NOT NULL,
    trust_name TEXT,
    domain TEXT,
    sub_domain TEXT,
    metric_id TEXT NOT NULL,
    metric_description TEXT,
    reporting_date TEXT NOT NULL,
    units TEXT,
    value NUMERIC,
    median_value NUMERIC,
    lower_quartile NUMERIC,
    upper_quartile NUMERIC,
    rank NUMERIC,
    PRIMARY KEY (org_code, metric_id, reporting_date)
);

COMMENT ON TABLE performance_data.oversight_metrics_raw IS 'NHS Oversight Framework raw metrics across multiple performance domains.';

-- -----------------------------------------------------------------------------
-- Table: oversight_league_table_raw
-- Purpose: NHS Oversight Framework league table with trust scores and segments
-- Source: database.py CREATE_OVERSIGHT_LEAGUE_TABLE_SQL
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS performance_data.oversight_league_table_raw (
    region TEXT,
    trust_type TEXT,
    trust_subtype TEXT,
    org_code TEXT NOT NULL,
    trust_name TEXT,
    reporting_date TEXT NOT NULL,
    average_score NUMERIC,
    likely_range_of_average_score TEXT,
    segment NUMERIC,
    trust_in_financial_deficit TEXT,
    rank NUMERIC,
    likely_range_of_rank TEXT,
    PRIMARY KEY (org_code, reporting_date)
);

COMMENT ON TABLE performance_data.oversight_league_table_raw IS 'NHS Oversight Framework league table with overall scores, segments, and rankings.';

-- -----------------------------------------------------------------------------
-- Table: dim_organisations
-- Purpose: Organisation dimension table (NHS trusts)
-- Source: database.py CREATE_DIM_ORGANISATIONS_SQL
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS performance_data.dim_organisations (
    org_code TEXT PRIMARY KEY,
    trust_name TEXT,
    region TEXT,
    trust_type TEXT,
    trust_subtype TEXT
);

COMMENT ON TABLE performance_data.dim_organisations IS 'Organisation dimension providing trust names and categorical attributes for cohort analysis.';

-- =============================================================================
-- SECTION 2: PERFORMANCE_DATA SCHEMA VIEWS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- View: rtt_trust_snapshot_v
-- Purpose: RTT snapshot with pct_within_18 calculated field for easy queries
-- Source: database.py CREATE_TRUST_SNAPSHOT_VIEW_SQL
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW performance_data.rtt_trust_snapshot_v AS
SELECT
  period,
  entity_level,
  org_code,
  org_name,
  rtt_part_type,
  completed_total,
  completed_within_18,
  compliance_18w,
  waiting_list_total,
  (1 - NULLIF(pct_over_18, 0))::DOUBLE PRECISION AS pct_within_18,
  median_weeks_completed,
  p95_weeks_completed,
  median_weeks_waiting,
  p92_weeks_waiting,
  over_18,
  over_26,
  over_40,
  over_52,
  over_65,
  over_78,
  unknown_clock_start
FROM performance_data.rtt_metrics_gold;

COMMENT ON VIEW performance_data.rtt_trust_snapshot_v IS 'RTT snapshot view with pct_within_18 calculated for dashboard consumption.';

-- -----------------------------------------------------------------------------
-- View: metric_values_base
-- Purpose: Unified long view across RTT, Cancer, Oversight with disaggregation
-- Source: Migration 004
-- -----------------------------------------------------------------------------

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

COMMENT ON VIEW performance_data.metric_values_base IS 'Unified long view across RTT, Cancer, and Oversight with disaggregation, roll-ups, and USC vs All gaps.';
COMMENT ON COLUMN performance_data.metric_values_base.disagg_key IS 'Canonical key of disaggregation signature used to scope percentile windows.';

-- =============================================================================
-- SECTION 3: MATERIALIZED VIEW WITH BENCHMARKING
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Materialized View: insight_metrics_long
-- Purpose: Benchmarked metrics with percentiles and normalized scores
-- Source: Migration 004
-- -----------------------------------------------------------------------------

DROP MATERIALIZED VIEW IF EXISTS performance_data.insight_metrics_long CASCADE;

CREATE MATERIALIZED VIEW performance_data.insight_metrics_long AS
WITH base AS (
  SELECT * FROM performance_data.metric_values_base WHERE valid_sample IS DISTINCT FROM FALSE
),
ranked AS (
  SELECT
    b.*,
    -- Partition by disagg_key to ensure apples-to-apples comparisons
    -- (e.g., RTT 'Overall' pathway vs 'Overall', not vs 'Part_1A')
    percent_rank() OVER (
      PARTITION BY b.metric_id, b.period, b.disagg_key
      ORDER BY CASE WHEN b.higher_is_better THEN b.value ELSE -b.value END
    ) AS percentile_overall,
    percent_rank() OVER (
      PARTITION BY b.metric_id, b.period, b.disagg_key, b.trust_type
      ORDER BY CASE WHEN b.higher_is_better THEN b.value ELSE -b.value END
    ) AS percentile_trust_type,
    percent_rank() OVER (
      PARTITION BY b.metric_id, b.period, b.disagg_key, b.trust_type, b.trust_subtype
      ORDER BY CASE WHEN b.higher_is_better THEN b.value ELSE -b.value END
    ) AS percentile_trust_subtype
  FROM base b
)
SELECT
  period,
  metric_id,
  metric_label,
  domain,
  org_code,
  org_name,
  region,
  trust_type,
  trust_subtype,
  referral_route,
  cancer_type,
  rtt_part_type,
  entity_level,
  value,
  unit,
  numerator,
  denominator,
  valid_sample,
  target_threshold,
  target_met,
  higher_is_better,
  is_rollup,
  rollup_method,
  disagg_key,
  -- Apply inversion for "lower is better" metrics to percentile columns
  CASE WHEN higher_is_better THEN percentile_overall ELSE 1 - percentile_overall END AS percentile_overall,
  CASE WHEN higher_is_better THEN percentile_trust_type ELSE 1 - percentile_trust_type END AS percentile_trust_type,
  CASE WHEN higher_is_better THEN percentile_trust_subtype ELSE 1 - percentile_trust_subtype END AS percentile_trust_subtype,
  ROUND((100 * (CASE WHEN higher_is_better THEN percentile_overall ELSE 1 - percentile_overall END))::NUMERIC, 1) AS normalised_score_0_100_overall,
  NOW() AS last_refreshed_at
FROM ranked;

COMMENT ON MATERIALIZED VIEW performance_data.insight_metrics_long IS 'Benchmarked metrics with overall/type/subtype percentiles and 0–100 score; period- and grain-consistent. Percentiles are direction-corrected: higher percentile always means better performance.';
COMMENT ON COLUMN performance_data.insight_metrics_long.percentile_overall IS 'Percentile within metric × period × disaggregation, across all providers (0..1). Partitioned by disagg_key to ensure apples-to-apples comparisons (e.g., RTT Overall vs Overall, not vs Part_1A). Direction-corrected: inverted for "lower is better" metrics so higher percentile always means better performance.';
COMMENT ON COLUMN performance_data.insight_metrics_long.percentile_trust_type IS 'Percentile within same trust_type cohort (0..1). Direction-corrected: inverted for "lower is better" metrics so higher percentile always means better performance.';
COMMENT ON COLUMN performance_data.insight_metrics_long.percentile_trust_subtype IS 'Percentile within same trust_subtype cohort (0..1). Direction-corrected: inverted for "lower is better" metrics so higher percentile always means better performance.';
COMMENT ON COLUMN performance_data.insight_metrics_long.normalised_score_0_100_overall IS '0–100 score where higher is always better, derived from direction-corrected percentile_overall.';

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_insight_metrics_long_org ON performance_data.insight_metrics_long (org_code);
CREATE INDEX IF NOT EXISTS idx_insight_metrics_long_metric_period ON performance_data.insight_metrics_long (metric_id, period);
CREATE INDEX IF NOT EXISTS idx_insight_metrics_long_cohorts ON performance_data.insight_metrics_long (trust_type, trust_subtype, region);

-- -----------------------------------------------------------------------------
-- View: insight_metrics_latest
-- Purpose: Latest period per metric×grain for fast dashboards
-- Source: Migration 004
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW performance_data.insight_metrics_latest AS
SELECT im.*
FROM performance_data.insight_metrics_long im
JOIN (
  SELECT metric_id, disagg_key, MAX(period) AS max_period
  FROM performance_data.insight_metrics_long
  GROUP BY metric_id, disagg_key
) mx
  ON im.metric_id = mx.metric_id AND im.disagg_key = mx.disagg_key AND im.period = mx.max_period;

COMMENT ON VIEW performance_data.insight_metrics_latest IS 'Latest period per metric×disaggregation for fast dashboards.';

-- =============================================================================
-- SECTION 4: PUBLIC SCHEMA VIEWS (API EXPOSURE)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS public;

-- -----------------------------------------------------------------------------
-- Public Views for PostgREST API Access
-- Source: Migration 006
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.performance_insight_metrics_latest AS
SELECT * FROM performance_data.insight_metrics_latest;

CREATE OR REPLACE VIEW public.performance_insight_metrics_long AS
SELECT * FROM performance_data.insight_metrics_long;

CREATE OR REPLACE VIEW public.performance_dim_organisations AS
SELECT org_code, trust_name, region, trust_type, trust_subtype
FROM performance_data.dim_organisations;

-- =============================================================================
-- SECTION 5: SEED DATA
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Seed: RTT Metrics (5 metrics)
-- Source: Migration 003
-- -----------------------------------------------------------------------------

INSERT INTO performance_data.metric_catalogue (
  metric_id, metric_label, domain, unit, higher_is_better, target_threshold, min_denominator, disaggregation_dims, source_table, notes
) VALUES
  ('rtt_pct_within_18', 'RTT waiting list: % within 18 weeks (stock)', 'rtt', 'percentage', true, NULL, 50, ARRAY['rtt_part_type','entity_level'], 'performance_data.rtt_trust_snapshot', 'Derived waiting list percentage under 18 weeks from rtt_trust_snapshot'),
  ('rtt_pct_over_52', 'RTT waiting list: % over 52 weeks (stock)', 'rtt', 'percentage', false, NULL, 50, ARRAY['rtt_part_type','entity_level'], 'performance_data.rtt_trust_snapshot', 'Share of known waiting list over 52 weeks'),
  ('rtt_p92_weeks_waiting', 'RTT waiting list: 92nd percentile weeks (stock)', 'rtt', 'weeks', false, NULL, 50, ARRAY['rtt_part_type','entity_level'], 'performance_data.rtt_trust_snapshot', 'Estimated 92nd percentile waiting time'),
  ('rtt_compliance_18w', 'RTT completed pathways: % within 18 weeks (flow)', 'rtt', 'percentage', true, NULL, 50, ARRAY['rtt_part_type','entity_level'], 'performance_data.rtt_trust_snapshot', 'Compliance on completed pathways within 18 weeks'),
  ('rtt_unknown_clock_start_rate', 'RTT: % unknown clock start (data quality)', 'rtt', 'percentage', false, NULL, 50, ARRAY['rtt_part_type','entity_level'], 'performance_data.rtt_trust_snapshot', 'Share of incomplete pathways with unknown clock start; proxy for PTL hygiene')
ON CONFLICT (metric_id) DO UPDATE SET
  metric_label = EXCLUDED.metric_label,
  domain = EXCLUDED.domain,
  unit = EXCLUDED.unit,
  higher_is_better = EXCLUDED.higher_is_better,
  target_threshold = EXCLUDED.target_threshold,
  min_denominator = EXCLUDED.min_denominator,
  disaggregation_dims = EXCLUDED.disaggregation_dims,
  source_table = EXCLUDED.source_table,
  notes = EXCLUDED.notes;

-- -----------------------------------------------------------------------------
-- Seed: Cancer Metrics (3 metrics)
-- Source: Migration 003
-- -----------------------------------------------------------------------------

INSERT INTO performance_data.metric_catalogue (
  metric_id, metric_label, domain, unit, higher_is_better, target_threshold, min_denominator, disaggregation_dims, source_table, notes
) VALUES
  ('cancer_28d_pct_within_target', 'Cancer 28-day FDS: % within target', 'cancer', 'percentage', true, 0.75, 20, ARRAY['referral_route','cancer_type'], 'performance_data.cancer_target_metrics', 'Faster Diagnosis Standard; target 75%'),
  ('cancer_31d_pct_within_target', 'Cancer 31-day: % first treatment within 31 days', 'cancer', 'percentage', true, 0.96, 20, ARRAY['referral_route','cancer_type'], 'performance_data.cancer_target_metrics', '31-day standard; common target 96%'),
  ('cancer_62d_pct_within_target', 'Cancer 62-day: % treatment within 62 days', 'cancer', 'percentage', true, 0.85, 20, ARRAY['referral_route','cancer_type'], 'performance_data.cancer_target_metrics', '62-day standard; target often 85%')
ON CONFLICT (metric_id) DO UPDATE SET
  metric_label = EXCLUDED.metric_label,
  domain = EXCLUDED.domain,
  unit = EXCLUDED.unit,
  higher_is_better = EXCLUDED.higher_is_better,
  target_threshold = EXCLUDED.target_threshold,
  min_denominator = EXCLUDED.min_denominator,
  disaggregation_dims = EXCLUDED.disaggregation_dims,
  source_table = EXCLUDED.source_table,
  notes = EXCLUDED.notes;

-- -----------------------------------------------------------------------------
-- Seed: Oversight Metrics (2 metrics)
-- Source: Migration 003
-- -----------------------------------------------------------------------------

INSERT INTO performance_data.metric_catalogue (
  metric_id, metric_label, domain, unit, higher_is_better, target_threshold, min_denominator, disaggregation_dims, source_table, notes
) VALUES
  ('oversight_average_score', 'Oversight: average metric score', 'oversight', 'score', true, NULL, NULL, ARRAY[]::TEXT[], 'performance_data.oversight_league_table_raw', 'Framework composite score; period varies'),
  ('oversight_segment_inverse', 'Oversight: segment (higher is better, inverted)', 'oversight', 'ordinal', true, NULL, NULL, ARRAY[]::TEXT[], 'performance_data.oversight_league_table_raw', 'Inverted segmentation (1 best → 4 worst mapped to higher-is-better)')
ON CONFLICT (metric_id) DO UPDATE SET
  metric_label = EXCLUDED.metric_label,
  domain = EXCLUDED.domain,
  unit = EXCLUDED.unit,
  higher_is_better = EXCLUDED.higher_is_better,
  target_threshold = EXCLUDED.target_threshold,
  min_denominator = EXCLUDED.min_denominator,
  disaggregation_dims = EXCLUDED.disaggregation_dims,
  source_table = EXCLUDED.source_table,
  notes = EXCLUDED.notes;

-- -----------------------------------------------------------------------------
-- Seed: Gap Metrics (3 metrics)
-- Source: Migration 005
-- -----------------------------------------------------------------------------

INSERT INTO performance_data.metric_catalogue (
  metric_id, metric_label, domain, unit, higher_is_better, target_threshold, min_denominator, disaggregation_dims, source_table, notes
) VALUES
  ('cancer_28d_gap_usc_all', 'Cancer 28-day: USC minus All Routes (pp)', 'cancer', 'percentage', true, NULL, 20, ARRAY['cancer_type'], 'performance_data.insight_metrics_long', 'Positive gap means USC route outperforms All Routes; derived'),
  ('cancer_31d_gap_usc_all', 'Cancer 31-day: USC minus All Routes (pp)', 'cancer', 'percentage', true, NULL, 20, ARRAY['cancer_type'], 'performance_data.insight_metrics_long', 'Positive gap means USC route outperforms All Routes; derived'),
  ('cancer_62d_gap_usc_all', 'Cancer 62-day: USC minus All Routes (pp)', 'cancer', 'percentage', true, NULL, 20, ARRAY['cancer_type'], 'performance_data.insight_metrics_long', 'Positive gap means USC route outperforms All Routes; derived')
ON CONFLICT (metric_id) DO UPDATE SET
  metric_label = EXCLUDED.metric_label,
  domain = EXCLUDED.domain,
  unit = EXCLUDED.unit,
  higher_is_better = EXCLUDED.higher_is_better,
  target_threshold = EXCLUDED.target_threshold,
  min_denominator = EXCLUDED.min_denominator,
  disaggregation_dims = EXCLUDED.disaggregation_dims,
  source_table = EXCLUDED.source_table,
  notes = EXCLUDED.notes;

-- =============================================================================
-- SECTION 6: GRANTS
-- =============================================================================

-- Grants for PostgREST API access
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON public.performance_insight_metrics_latest TO anon, authenticated;
GRANT SELECT ON public.performance_insight_metrics_long TO anon, authenticated;
GRANT SELECT ON public.performance_dim_organisations TO anon, authenticated;

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
-- This migration creates a fully self-contained performance_data schema with:
-- ✓ 6 core tables
-- ✓ 4 views (3 in performance_data, 1 calculated view, 1 materialized view)
-- ✓ 3 public schema views for API access
-- ✓ 3 indexes on materialized view
-- ✓ 10 metric catalogue seed records
-- ✓ Comprehensive documentation via COMMENT statements
-- ✓ API access grants
--
-- Schema: performance_data (isolated, self-contained)
-- Public exposure: Via thin views in public schema for PostgREST
-- Dependencies: None (can run standalone)
-- Supersedes: Migrations 002-006
-- =============================================================================
