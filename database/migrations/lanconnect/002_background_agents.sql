-- Migration 002: Background Agents Support
-- Adds support for scheduled background agents using LangGraph's cron API
-- This migration adds metadata columns to threads_mirror and creates cron_jobs table

SET search_path = langconnect, public;

-- ============================================================================
-- THREADS METADATA: Add background agent tracking columns
-- ============================================================================

-- Add new columns to threads_mirror for background agent tracking
ALTER TABLE langconnect.threads_mirror
ADD COLUMN IF NOT EXISTS is_background_run BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS has_user_message BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS opened_in_chat BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS cron_id TEXT,
ADD COLUMN IF NOT EXISTS last_user_message_at TIMESTAMPTZ;

-- Add comments for new columns
COMMENT ON COLUMN langconnect.threads_mirror.is_background_run IS 'True if thread was created by a cron job';
COMMENT ON COLUMN langconnect.threads_mirror.has_user_message IS 'True if user has sent at least one message (used for chat sidebar filtering)';
COMMENT ON COLUMN langconnect.threads_mirror.opened_in_chat IS 'True if user has clicked "Open in Chat" on a background thread';
COMMENT ON COLUMN langconnect.threads_mirror.cron_id IS 'ID of the cron job that created this thread (if applicable)';
COMMENT ON COLUMN langconnect.threads_mirror.last_user_message_at IS 'Timestamp of last user message (for chat sidebar sorting)';

-- ============================================================================
-- INDEXES: Add indexes for efficient background agent queries
-- ============================================================================

-- Index for background thread filtering (background dashboard)
CREATE INDEX IF NOT EXISTS idx_threads_mirror_background
ON langconnect.threads_mirror(is_background_run, has_user_message);

-- Index for chat sidebar filtering (only threads with user messages)
CREATE INDEX IF NOT EXISTS idx_threads_mirror_chat
ON langconnect.threads_mirror(has_user_message, last_user_message_at DESC)
WHERE has_user_message = true;

-- Index for cron-specific thread queries
CREATE INDEX IF NOT EXISTS idx_threads_mirror_cron_id
ON langconnect.threads_mirror(cron_id)
WHERE cron_id IS NOT NULL;

-- ============================================================================
-- CRON JOBS TABLE: Mirror of LangGraph cron jobs for quick lookups
-- ============================================================================

CREATE TABLE IF NOT EXISTS langconnect.cron_jobs (
  cron_id TEXT PRIMARY KEY,
  user_id UUID NOT NULL,
  assistant_id UUID NOT NULL,
  deployment_id TEXT NOT NULL,
  graph_id TEXT,
  schedule TEXT NOT NULL,
  cron_name TEXT,
  payload JSONB,
  next_run_at TIMESTAMPTZ,
  last_run_at TIMESTAMPTZ,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'error', 'deleted')),
  error_message TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Foreign key to assistants_mirror (optional, can be null if assistant is deleted)
  CONSTRAINT fk_cron_jobs_assistant FOREIGN KEY (assistant_id)
    REFERENCES langconnect.assistants_mirror(assistant_id) ON DELETE SET NULL
);

-- Comments for cron_jobs table
COMMENT ON TABLE langconnect.cron_jobs IS 'Mirror of LangGraph cron jobs for observability and background agent management';
COMMENT ON COLUMN langconnect.cron_jobs.cron_id IS 'LangGraph cron job identifier';
COMMENT ON COLUMN langconnect.cron_jobs.user_id IS 'User who created this cron job';
COMMENT ON COLUMN langconnect.cron_jobs.assistant_id IS 'Assistant that will be executed by this cron';
COMMENT ON COLUMN langconnect.cron_jobs.deployment_id IS 'LangGraph deployment ID';
COMMENT ON COLUMN langconnect.cron_jobs.graph_id IS 'Graph ID (derived from assistant)';
COMMENT ON COLUMN langconnect.cron_jobs.schedule IS 'Cron schedule expression';
COMMENT ON COLUMN langconnect.cron_jobs.cron_name IS 'User-friendly name for the cron job';
COMMENT ON COLUMN langconnect.cron_jobs.payload IS 'Input payload for cron execution';
COMMENT ON COLUMN langconnect.cron_jobs.next_run_at IS 'Next scheduled execution time';
COMMENT ON COLUMN langconnect.cron_jobs.last_run_at IS 'Last execution time';
COMMENT ON COLUMN langconnect.cron_jobs.status IS 'Cron job status: active, paused, error, deleted';
COMMENT ON COLUMN langconnect.cron_jobs.error_message IS 'Error message if status is error';
COMMENT ON COLUMN langconnect.cron_jobs.metadata IS 'Additional metadata from LangGraph';

-- Indexes for cron_jobs table
CREATE INDEX IF NOT EXISTS idx_cron_jobs_user ON langconnect.cron_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_assistant ON langconnect.cron_jobs(assistant_id);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_status ON langconnect.cron_jobs(status);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_next_run ON langconnect.cron_jobs(next_run_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_cron_jobs_created ON langconnect.cron_jobs(created_at DESC);

-- Trigger for updated_at
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_cron_jobs_updated_at') THEN
    CREATE TRIGGER trigger_cron_jobs_updated_at
    BEFORE UPDATE ON langconnect.cron_jobs
    FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

-- ============================================================================
-- CACHE STATE: Add cron_jobs version tracking
-- ============================================================================

-- Add cron_jobs_version column to cache_state if it doesn't exist
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'langconnect'
    AND table_name = 'cache_state'
    AND column_name = 'cron_jobs_version'
  ) THEN
    ALTER TABLE langconnect.cache_state
    ADD COLUMN cron_jobs_version BIGINT NOT NULL DEFAULT 1;
  END IF;
END $$;

COMMENT ON COLUMN langconnect.cache_state.cron_jobs_version IS 'Incremented when cron_jobs table changes';

-- ============================================================================
-- FUNCTIONS: Update upsert_thread_mirror to handle new metadata fields
-- ============================================================================

-- Drop and recreate the upsert_thread_mirror function with new metadata parameters
CREATE OR REPLACE FUNCTION langconnect.upsert_thread_mirror(
    p_thread_id UUID,
    p_assistant_id UUID,
    p_graph_id TEXT,
    p_user_id TEXT,
    p_name TEXT,
    p_status TEXT,
    p_last_message_at TIMESTAMPTZ,
    p_langgraph_created_at TIMESTAMPTZ,
    p_langgraph_updated_at TIMESTAMPTZ,
    p_is_background_run BOOLEAN DEFAULT NULL,
    p_has_user_message BOOLEAN DEFAULT NULL,
    p_opened_in_chat BOOLEAN DEFAULT NULL,
    p_cron_id TEXT DEFAULT NULL,
    p_last_user_message_at TIMESTAMPTZ DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    version_incremented BOOLEAN := FALSE;
    existing_thread RECORD;
BEGIN
    SELECT * INTO existing_thread
    FROM langconnect.threads_mirror
    WHERE thread_id = p_thread_id;

    INSERT INTO langconnect.threads_mirror (
        thread_id, assistant_id, graph_id, user_id, name, status,
        last_message_at, langgraph_created_at, langgraph_updated_at,
        is_background_run, has_user_message, opened_in_chat, cron_id, last_user_message_at
    ) VALUES (
        p_thread_id, p_assistant_id, p_graph_id, p_user_id, p_name, p_status,
        p_last_message_at, p_langgraph_created_at, p_langgraph_updated_at,
        p_is_background_run, p_has_user_message, p_opened_in_chat, p_cron_id, p_last_user_message_at
    )
    ON CONFLICT (thread_id) DO UPDATE SET
        assistant_id = COALESCE(EXCLUDED.assistant_id, threads_mirror.assistant_id),
        graph_id = COALESCE(EXCLUDED.graph_id, threads_mirror.graph_id),
        user_id = COALESCE(EXCLUDED.user_id, threads_mirror.user_id),
        name = CASE
            WHEN EXCLUDED.name IS NOT NULL THEN EXCLUDED.name
            ELSE threads_mirror.name
        END,
        status = COALESCE(EXCLUDED.status, threads_mirror.status),
        last_message_at = COALESCE(EXCLUDED.last_message_at, threads_mirror.last_message_at),
        langgraph_created_at = EXCLUDED.langgraph_created_at,
        langgraph_updated_at = COALESCE(EXCLUDED.langgraph_updated_at, threads_mirror.langgraph_updated_at),
        -- Update background metadata fields if provided
        is_background_run = COALESCE(EXCLUDED.is_background_run, threads_mirror.is_background_run),
        has_user_message = COALESCE(EXCLUDED.has_user_message, threads_mirror.has_user_message),
        opened_in_chat = COALESCE(EXCLUDED.opened_in_chat, threads_mirror.opened_in_chat),
        cron_id = COALESCE(EXCLUDED.cron_id, threads_mirror.cron_id),
        last_user_message_at = COALESCE(EXCLUDED.last_user_message_at, threads_mirror.last_user_message_at),
        mirror_updated_at = CASE
            WHEN threads_mirror.assistant_id IS DISTINCT FROM COALESCE(EXCLUDED.assistant_id, threads_mirror.assistant_id) OR
                 threads_mirror.status IS DISTINCT FROM COALESCE(EXCLUDED.status, threads_mirror.status) OR
                 threads_mirror.last_message_at IS DISTINCT FROM COALESCE(EXCLUDED.last_message_at, threads_mirror.last_message_at) OR
                 threads_mirror.name IS DISTINCT FROM (CASE WHEN EXCLUDED.name IS NOT NULL THEN EXCLUDED.name ELSE threads_mirror.name END) OR
                 threads_mirror.has_user_message IS DISTINCT FROM COALESCE(EXCLUDED.has_user_message, threads_mirror.has_user_message) OR
                 threads_mirror.opened_in_chat IS DISTINCT FROM COALESCE(EXCLUDED.opened_in_chat, threads_mirror.opened_in_chat)
            THEN NOW()
            ELSE threads_mirror.mirror_updated_at
        END,
        updated_at = CASE
            WHEN threads_mirror.assistant_id IS DISTINCT FROM COALESCE(EXCLUDED.assistant_id, threads_mirror.assistant_id) OR
                 threads_mirror.status IS DISTINCT FROM COALESCE(EXCLUDED.status, threads_mirror.status) OR
                 threads_mirror.last_message_at IS DISTINCT FROM COALESCE(EXCLUDED.last_message_at, threads_mirror.last_message_at) OR
                 threads_mirror.name IS DISTINCT FROM (CASE WHEN EXCLUDED.name IS NOT NULL THEN EXCLUDED.name ELSE threads_mirror.name END) OR
                 threads_mirror.has_user_message IS DISTINCT FROM COALESCE(EXCLUDED.has_user_message, threads_mirror.has_user_message) OR
                 threads_mirror.opened_in_chat IS DISTINCT FROM COALESCE(EXCLUDED.opened_in_chat, threads_mirror.opened_in_chat)
            THEN NOW()
            ELSE threads_mirror.updated_at
        END;

    -- Increment cache version if thread was created or key fields changed
    IF existing_thread IS NULL OR
       existing_thread.assistant_id IS DISTINCT FROM p_assistant_id OR
       existing_thread.status IS DISTINCT FROM p_status OR
       existing_thread.last_message_at IS DISTINCT FROM p_last_message_at OR
       existing_thread.has_user_message IS DISTINCT FROM p_has_user_message OR
       existing_thread.opened_in_chat IS DISTINCT FROM p_opened_in_chat THEN
        PERFORM langconnect.increment_cache_version('threads');
        version_incremented := TRUE;
    END IF;

    RETURN version_incremented;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION langconnect.upsert_thread_mirror IS 'Upsert thread mirror record with optional background agent metadata';

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
