-- Migration 018: Preserve agent_run_costs when threads are deleted
--
-- Problem: The original ON DELETE CASCADE on thread_id causes cost records
-- to be deleted when a user deletes a thread/conversation. This is problematic:
-- - Users lose their billing/usage history
-- - Analytics and cost reporting become inaccurate over time
-- - Audit trail for financial data is lost
--
-- Solution: Change to ON DELETE SET NULL so cost records are preserved
-- with a null thread_id when the associated thread is deleted.

SET search_path = langconnect, public;

-- Step 1: Make thread_id nullable (required for SET NULL behavior)
ALTER TABLE langconnect.agent_run_costs
    ALTER COLUMN thread_id DROP NOT NULL;

-- Step 2: Drop the existing CASCADE foreign key constraint
ALTER TABLE langconnect.agent_run_costs
    DROP CONSTRAINT IF EXISTS fk_agent_run_costs_thread;

-- Step 3: Add new foreign key with SET NULL behavior
ALTER TABLE langconnect.agent_run_costs
    ADD CONSTRAINT fk_agent_run_costs_thread
    FOREIGN KEY (thread_id)
    REFERENCES langconnect.threads_mirror(thread_id)
    ON DELETE SET NULL;

-- Comments for documentation
COMMENT ON COLUMN langconnect.agent_run_costs.thread_id IS
    'Thread ID for this run. NULL if the thread was deleted (cost records preserved for billing history)';
