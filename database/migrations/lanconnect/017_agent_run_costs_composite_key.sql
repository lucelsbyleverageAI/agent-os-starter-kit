-- Migration 017: Update agent_run_costs unique constraint for multi-model runs
--
-- Problem: The original UNIQUE(run_id) constraint assumed one cost entry per run.
-- However, agents like deepagent can use multiple models within a single run:
-- - Main agent might use Gemini
-- - Sub-agent might use Grok
-- Both share the same run_id, but we need separate cost records.
--
-- Solution: Change the unique constraint to (run_id, model_name) to allow
-- one record per model per run.

SET search_path = langconnect, public;

-- Step 1: Drop the existing unique constraint on run_id
-- The constraint was created implicitly, so we need to find its name
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    -- Find the unique constraint name for run_id column
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'langconnect.agent_run_costs'::regclass
      AND contype = 'u'
      AND array_length(conkey, 1) = 1
      AND conkey[1] = (
          SELECT attnum FROM pg_attribute
          WHERE attrelid = 'langconnect.agent_run_costs'::regclass
          AND attname = 'run_id'
      );

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE langconnect.agent_run_costs DROP CONSTRAINT %I', constraint_name);
        RAISE NOTICE 'Dropped constraint: %', constraint_name;
    ELSE
        RAISE NOTICE 'No unique constraint found on run_id column';
    END IF;
END $$;

-- Step 2: Add composite unique constraint on (run_id, model_name)
-- This allows one record per model per run, supporting multi-model agents
ALTER TABLE langconnect.agent_run_costs
    ADD CONSTRAINT agent_run_costs_run_model_unique UNIQUE (run_id, model_name);

-- Step 3: Add index for run_id lookups (since we removed the unique constraint)
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_run_id
    ON langconnect.agent_run_costs(run_id);

-- Comments for documentation
COMMENT ON CONSTRAINT agent_run_costs_run_model_unique ON langconnect.agent_run_costs IS
    'Allows one cost record per model per run, supporting multi-model agents like deepagent';
