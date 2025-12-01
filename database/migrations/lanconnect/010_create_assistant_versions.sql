-- Assistant Version History
-- Mirrors LangGraph version history locally for fast reads with optional commit messages
-- Idempotent and safe to re-run

SET search_path = langconnect, public;

-- ============================================================================
-- ASSISTANT VERSION HISTORY TABLE
-- ============================================================================

-- Create assistant versions table to store version history
CREATE TABLE IF NOT EXISTS langconnect.assistant_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assistant_id UUID NOT NULL,
  version INTEGER NOT NULL,

  -- Mirrored from LangGraph version data
  name TEXT NOT NULL,
  description TEXT,
  config JSONB NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}',
  tags TEXT[] NOT NULL DEFAULT '{}',  -- Agent categorization tags

  -- Local-only fields for audit trail
  commit_message TEXT,  -- Optional user-provided change description
  created_by VARCHAR,   -- User ID who created this version

  -- Timestamps
  langgraph_created_at TIMESTAMPTZ NOT NULL,  -- When version was created in LangGraph
  mirror_created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- When we mirrored it

  -- Constraints
  UNIQUE(assistant_id, version),
  CONSTRAINT fk_assistant_versions_assistant
    FOREIGN KEY (assistant_id)
    REFERENCES langconnect.assistants_mirror(assistant_id)
    ON DELETE CASCADE
);

-- Add tags column if it doesn't exist (for existing installations)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'langconnect'
    AND table_name = 'assistant_versions'
    AND column_name = 'tags'
  ) THEN
    ALTER TABLE langconnect.assistant_versions ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}';
  END IF;
END $$;

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Index for fast lookups by assistant_id
CREATE INDEX IF NOT EXISTS idx_assistant_versions_assistant_id
  ON langconnect.assistant_versions(assistant_id);

-- Index for efficient version ordering (most recent first)
CREATE INDEX IF NOT EXISTS idx_assistant_versions_lookup
  ON langconnect.assistant_versions(assistant_id, version DESC);

-- Index for timestamp-based queries
CREATE INDEX IF NOT EXISTS idx_assistant_versions_created_at
  ON langconnect.assistant_versions(langgraph_created_at DESC);

-- ============================================================================
-- ADD VERSIONS_VERSION TO CACHE_STATE
-- ============================================================================

-- Add versions_version column for cache invalidation
ALTER TABLE langconnect.cache_state
ADD COLUMN IF NOT EXISTS versions_version BIGINT NOT NULL DEFAULT 1;

-- ============================================================================
-- UPDATE INCREMENT_CACHE_VERSION FUNCTION
-- ============================================================================

-- Update the increment_cache_version function to handle 'versions' type
CREATE OR REPLACE FUNCTION langconnect.increment_cache_version(
    version_type TEXT
) RETURNS BIGINT AS $$
DECLARE
    new_version BIGINT;
BEGIN
    UPDATE langconnect.cache_state
    SET
        graphs_version = CASE WHEN version_type = 'graphs' THEN graphs_version + 1 ELSE graphs_version END,
        assistants_version = CASE WHEN version_type = 'assistants' THEN assistants_version + 1 ELSE assistants_version END,
        schemas_version = CASE WHEN version_type = 'schemas' THEN schemas_version + 1 ELSE schemas_version END,
        graph_schemas_version = CASE WHEN version_type = 'graph_schemas' THEN graph_schemas_version + 1 ELSE graph_schemas_version END,
        threads_version = CASE WHEN version_type = 'threads' THEN threads_version + 1 ELSE threads_version END,
        versions_version = CASE WHEN version_type = 'versions' THEN versions_version + 1 ELSE versions_version END,
        updated_at = NOW()
    WHERE id = 1;

    SELECT
        CASE
            WHEN version_type = 'graphs' THEN graphs_version
            WHEN version_type = 'assistants' THEN assistants_version
            WHEN version_type = 'schemas' THEN schemas_version
            WHEN version_type = 'graph_schemas' THEN graph_schemas_version
            WHEN version_type = 'threads' THEN threads_version
            WHEN version_type = 'versions' THEN versions_version
            ELSE 0
        END
    INTO new_version
    FROM langconnect.cache_state
    WHERE id = 1;

    RETURN new_version;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- UPSERT FUNCTION FOR ASSISTANT VERSIONS
-- ============================================================================

-- Upsert assistant version with optional commit message
CREATE OR REPLACE FUNCTION langconnect.upsert_assistant_version(
    p_assistant_id UUID,
    p_version INTEGER,
    p_name TEXT,
    p_description TEXT,
    p_config JSONB,
    p_metadata JSONB,
    p_langgraph_created_at TIMESTAMPTZ,
    p_commit_message TEXT DEFAULT NULL,
    p_created_by VARCHAR DEFAULT NULL,
    p_tags TEXT[] DEFAULT '{}'
) RETURNS BOOLEAN AS $$
DECLARE
    version_inserted BOOLEAN := FALSE;
BEGIN
    INSERT INTO langconnect.assistant_versions (
        assistant_id,
        version,
        name,
        description,
        config,
        metadata,
        tags,
        langgraph_created_at,
        commit_message,
        created_by
    ) VALUES (
        p_assistant_id,
        p_version,
        p_name,
        p_description,
        p_config,
        p_metadata,
        COALESCE(p_tags, '{}'),
        p_langgraph_created_at,
        p_commit_message,
        p_created_by
    )
    ON CONFLICT (assistant_id, version) DO UPDATE SET
        -- Only update commit_message and created_by if they were NULL before
        -- This allows enriching version records after they're created
        commit_message = COALESCE(assistant_versions.commit_message, EXCLUDED.commit_message),
        created_by = COALESCE(assistant_versions.created_by, EXCLUDED.created_by);

    -- Check if we actually inserted a new row
    GET DIAGNOSTICS version_inserted = ROW_COUNT;

    IF version_inserted THEN
        PERFORM langconnect.increment_cache_version('versions');
    END IF;

    RETURN version_inserted;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- FUNCTION TO UPDATE COMMIT MESSAGE FOR EXISTING VERSION
-- ============================================================================

-- Update commit message for a specific version (used when saving with commit message)
CREATE OR REPLACE FUNCTION langconnect.update_version_commit_message(
    p_assistant_id UUID,
    p_version INTEGER,
    p_commit_message TEXT,
    p_created_by VARCHAR DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    rows_updated INTEGER;
BEGIN
    UPDATE langconnect.assistant_versions
    SET
        commit_message = p_commit_message,
        created_by = COALESCE(p_created_by, created_by)
    WHERE assistant_id = p_assistant_id
      AND version = p_version;

    GET DIAGNOSTICS rows_updated = ROW_COUNT;

    RETURN rows_updated > 0;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGER FOR UPDATED_AT (using existing function)
-- ============================================================================

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_assistant_versions_updated_at') THEN
    CREATE TRIGGER trigger_assistant_versions_updated_at
      BEFORE UPDATE ON langconnect.assistant_versions
      FOR EACH ROW
      EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE langconnect.assistant_versions IS 'Version history for assistants - mirrors LangGraph versions with optional local metadata (commit messages)';
COMMENT ON COLUMN langconnect.assistant_versions.assistant_id IS 'References the assistant this version belongs to';
COMMENT ON COLUMN langconnect.assistant_versions.version IS 'LangGraph version number (increments on each update)';
COMMENT ON COLUMN langconnect.assistant_versions.name IS 'Assistant name at this version';
COMMENT ON COLUMN langconnect.assistant_versions.description IS 'Assistant description at this version';
COMMENT ON COLUMN langconnect.assistant_versions.config IS 'Full assistant configuration at this version';
COMMENT ON COLUMN langconnect.assistant_versions.metadata IS 'Full assistant metadata at this version';
COMMENT ON COLUMN langconnect.assistant_versions.tags IS 'Agent categorization tags at this version';
COMMENT ON COLUMN langconnect.assistant_versions.commit_message IS 'Optional user-provided description of changes (local-only, not in LangGraph)';
COMMENT ON COLUMN langconnect.assistant_versions.created_by IS 'User ID who created this version (local-only)';
COMMENT ON COLUMN langconnect.assistant_versions.langgraph_created_at IS 'When this version was created in LangGraph';
COMMENT ON COLUMN langconnect.assistant_versions.mirror_created_at IS 'When this version was mirrored to local database';

COMMENT ON FUNCTION langconnect.upsert_assistant_version(UUID, INTEGER, TEXT, TEXT, JSONB, JSONB, TIMESTAMPTZ, TEXT, VARCHAR, TEXT[]) IS 'Upsert assistant version with optional commit message and tags, increments cache version on insert';
COMMENT ON FUNCTION langconnect.update_version_commit_message(UUID, INTEGER, TEXT, VARCHAR) IS 'Update commit message for an existing version (used when saving with commit message after version is created)';

COMMENT ON COLUMN langconnect.cache_state.versions_version IS 'Incremented when assistant_versions changes';

-- ============================================================================
-- RECORD MIGRATION
-- ============================================================================

INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('010', 'Create assistant_versions table for version history')
ON CONFLICT (version) DO NOTHING;
