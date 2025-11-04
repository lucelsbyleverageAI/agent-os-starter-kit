-- Migration: Fix cancer_target_metrics schema to support trust-level aggregates
-- Created: 2025-11-04
-- Purpose: Allow NULL values in schema and use empty strings in practice for trust aggregates
--
-- Context:
-- - Migration 002 created cancer_target_metrics with NOT NULL constraints
-- - Migration 005 created views that generate trust-level aggregates
-- - Pipeline now generates these aggregates via transforms.py aggregation logic
-- - Original PRIMARY KEY constraint prevented NULL values, causing inserts to fail
--
-- This migration:
-- 1. Drops PRIMARY KEY constraint (doesn't support NULLs)
-- 2. Allows NULL values in cancer_type and referral_route columns
-- 3. Creates simple unique constraint (works with ON CONFLICT upserts)
--
-- Implementation Note:
-- - Schema allows NULLs, but pipeline uses empty strings ('') for trust aggregates
-- - Empty strings enable proper unique constraint that works with ON CONFLICT
-- - Trust-level aggregates have cancer_type = '' and referral_route = 'ALL ROUTES'

-- -----------------------------------------------------------------------------
-- Step 1: Drop PRIMARY KEY constraint
-- -----------------------------------------------------------------------------
-- The original PRIMARY KEY included cancer_type and referral_route columns,
-- which prevented NULL values. We replace it with a unique index that handles NULLs.

ALTER TABLE performance_data.cancer_target_metrics
DROP CONSTRAINT IF EXISTS cancer_target_metrics_pkey;

-- -----------------------------------------------------------------------------
-- Step 2: Allow NULL values in cancer_type and referral_route
-- -----------------------------------------------------------------------------
-- Trust-level aggregates use cancer_type IS NULL to indicate "all cancer types"
-- Referral route can also be NULL in certain aggregation scenarios

ALTER TABLE performance_data.cancer_target_metrics
ALTER COLUMN cancer_type DROP NOT NULL,
ALTER COLUMN referral_route DROP NOT NULL;

-- -----------------------------------------------------------------------------
-- Step 3: Create simple unique constraint for ON CONFLICT upserts
-- -----------------------------------------------------------------------------
-- This constraint ensures uniqueness of (period, metric, org_code, cancer_type, referral_route)
-- and is compatible with PostgreSQL's ON CONFLICT clause used in pipeline upserts.
--
-- Design Choice:
-- - Simple unique constraint (not expression-based index with COALESCE)
-- - Works with ON CONFLICT DO UPDATE in pipeline code
-- - Pipeline uses empty strings ('') for trust aggregates, not NULLs
-- - Each trust has ONE aggregate row per period/metric with cancer_type = ''

ALTER TABLE performance_data.cancer_target_metrics
ADD CONSTRAINT cancer_target_metrics_unique_key
UNIQUE (period, metric, org_code, cancer_type, referral_route);

-- Add comment explaining the constraint behavior
COMMENT ON CONSTRAINT cancer_target_metrics_unique_key ON performance_data.cancer_target_metrics IS
'Unique constraint supporting trust-level aggregates (cancer_type = '''') and upsert operations. Pipeline uses empty strings for aggregates.';

-- -----------------------------------------------------------------------------
-- Verification query (for manual testing)
-- -----------------------------------------------------------------------------
-- After this migration, you should be able to insert trust-level aggregates:
--
-- INSERT INTO performance_data.cancer_target_metrics
--     (period, metric, org_code, cancer_type, referral_route,
--      within_target, outside_target, pct_within_target, org_name, metric_label)
-- VALUES
--     ('2025-08', 5, 'TEST', '', 'ALL ROUTES',
--      100, 10, 0.909, 'Test Trust', '31-day standard')
-- ON CONFLICT (period, metric, org_code, cancer_type, referral_route)
-- DO UPDATE SET within_target = EXCLUDED.within_target;
--
-- Expected: Success (no constraint violation)
-- Note: cancer_type = '' (empty string) represents trust-level aggregate
