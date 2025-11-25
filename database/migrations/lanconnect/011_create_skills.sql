-- Create Skills tables and storage bucket
-- Idempotent and safe to re-run

-- ============================================================================
-- SKILLS METADATA TABLE
-- ============================================================================

-- Skills metadata table
CREATE TABLE IF NOT EXISTS langconnect.skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) NOT NULL,
    description VARCHAR(1024) NOT NULL,
    storage_path TEXT NOT NULL,           -- Path in Supabase storage bucket
    pip_requirements TEXT[],              -- Optional pip packages to install
    created_by TEXT NOT NULL,             -- User ID
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Name constraints: lowercase, hyphens, numbers only, no reserved words
    CONSTRAINT valid_skill_name CHECK (
        name ~ '^[a-z0-9-]+$' AND
        LENGTH(name) >= 1 AND
        LENGTH(name) <= 64 AND
        name NOT LIKE '%anthropic%' AND
        name NOT LIKE '%claude%'
    ),
    CONSTRAINT valid_skill_description CHECK (
        LENGTH(description) >= 1 AND
        LENGTH(description) <= 1024
    )
);

-- Add unique constraint on name per user (users can't have duplicate skill names)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema = 'langconnect' AND table_name = 'skills' AND constraint_name = 'unique_skill_name_per_user'
  ) THEN
    ALTER TABLE langconnect.skills ADD CONSTRAINT unique_skill_name_per_user UNIQUE (name, created_by);
  END IF;
END $$;

-- Index for faster lookups by creator
CREATE INDEX IF NOT EXISTS idx_skills_created_by ON langconnect.skills(created_by);
CREATE INDEX IF NOT EXISTS idx_skills_name ON langconnect.skills(name);
CREATE INDEX IF NOT EXISTS idx_skills_created_at ON langconnect.skills(created_at DESC);

-- ============================================================================
-- SKILL PERMISSIONS TABLE
-- ============================================================================

-- Skills permissions table (mirrors collection_permissions pattern)
CREATE TABLE IF NOT EXISTS langconnect.skill_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID NOT NULL REFERENCES langconnect.skills(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    permission_level TEXT NOT NULL CHECK (permission_level IN ('viewer', 'editor', 'owner')),
    granted_by TEXT NOT NULL,  -- 'system:public' for auto-granted from public permissions
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(skill_id, user_id)
);

-- Indexes for skill permissions
CREATE INDEX IF NOT EXISTS idx_skill_permissions_user ON langconnect.skill_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_skill_permissions_skill ON langconnect.skill_permissions(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_permissions_level ON langconnect.skill_permissions(permission_level);

-- ============================================================================
-- PUBLIC SKILL PERMISSIONS TABLE
-- ============================================================================

-- Public skill permissions table (mirrors public_collection_permissions pattern)
-- This tracks which skills are publicly available to all users
CREATE TABLE IF NOT EXISTS langconnect.public_skill_permissions (
    id SERIAL PRIMARY KEY,
    skill_id UUID NOT NULL REFERENCES langconnect.skills(id) ON DELETE CASCADE,
    permission_level TEXT NOT NULL DEFAULT 'viewer' CHECK (permission_level IN ('viewer', 'editor')),
    created_by UUID NOT NULL,              -- Admin who created the public permission
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,                -- NULL if active, timestamp if revoked
    revoke_mode TEXT CHECK (revoke_mode IN ('revoke_all', 'future_only')),
    notes TEXT,                            -- Optional admin notes

    -- Constraints matching the collection pattern
    CONSTRAINT valid_skill_revoke_state CHECK (
        (revoked_at IS NULL AND revoke_mode IS NULL) OR
        (revoked_at IS NOT NULL AND revoke_mode IS NOT NULL)
    ),
    -- Only one active public permission per skill
    CONSTRAINT unique_active_skill_permission EXCLUDE (skill_id WITH =) WHERE (revoked_at IS NULL)
);

-- Index for active public permissions
CREATE INDEX IF NOT EXISTS idx_public_skill_permissions_active
    ON langconnect.public_skill_permissions(skill_id) WHERE revoked_at IS NULL;

-- ============================================================================
-- CACHE VERSION SUPPORT
-- ============================================================================

-- Add skills_version to cache_state table if it doesn't exist
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'langconnect' AND table_name = 'cache_state' AND column_name = 'skills_version'
  ) THEN
    ALTER TABLE langconnect.cache_state ADD COLUMN skills_version BIGINT NOT NULL DEFAULT 1;
  END IF;
END $$;

-- Update increment_cache_version function to support skills
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
        skills_version = CASE WHEN version_type = 'skills' THEN skills_version + 1 ELSE skills_version END,
        updated_at = NOW()
    WHERE id = 1;

    SELECT
        CASE
            WHEN version_type = 'graphs' THEN graphs_version
            WHEN version_type = 'assistants' THEN assistants_version
            WHEN version_type = 'schemas' THEN schemas_version
            WHEN version_type = 'graph_schemas' THEN graph_schemas_version
            WHEN version_type = 'threads' THEN threads_version
            WHEN version_type = 'skills' THEN skills_version
            ELSE 0
        END
    INTO new_version
    FROM langconnect.cache_state
    WHERE id = 1;

    RETURN new_version;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- AUTO-GRANT PUBLIC SKILL PERMISSIONS TO NEW USERS
-- ============================================================================

-- Update the auto_grant_public_permissions function to include skills
CREATE OR REPLACE FUNCTION langconnect.auto_grant_public_permissions()
RETURNS TRIGGER AS $$
BEGIN
  -- Grant all active public graph permissions to the new user
  INSERT INTO langconnect.graph_permissions (user_id, graph_id, permission_level, granted_by)
  SELECT NEW.id::VARCHAR, graph_id, permission_level, 'system:public'
  FROM langconnect.public_graph_permissions WHERE revoked_at IS NULL
  ON CONFLICT (user_id, graph_id) DO NOTHING;

  -- Grant all active public assistant permissions to the new user
  INSERT INTO langconnect.assistant_permissions (user_id, assistant_id, permission_level, granted_by)
  SELECT NEW.id::VARCHAR, assistant_id::UUID, permission_level, 'system:public'
  FROM langconnect.public_assistant_permissions WHERE revoked_at IS NULL
  ON CONFLICT (user_id, assistant_id) DO NOTHING;

  -- Grant all active public collection permissions to the new user
  INSERT INTO langconnect.collection_permissions (user_id, collection_id, permission_level, granted_by)
  SELECT NEW.id::VARCHAR, collection_id, permission_level, 'system:public'
  FROM langconnect.public_collection_permissions WHERE revoked_at IS NULL
  ON CONFLICT (collection_id, user_id) DO NOTHING;

  -- Grant all active public skill permissions to the new user
  INSERT INTO langconnect.skill_permissions (user_id, skill_id, permission_level, granted_by)
  SELECT NEW.id::VARCHAR, skill_id, permission_level, 'system:public'
  FROM langconnect.public_skill_permissions WHERE revoked_at IS NULL
  ON CONFLICT (skill_id, user_id) DO NOTHING;

  RETURN NEW;
END; $$ LANGUAGE plpgsql;

-- ============================================================================
-- BACKFILL PUBLIC PERMISSIONS FUNCTION UPDATE
-- ============================================================================

-- Drop existing function first since we're changing the return type (adding skills_granted column)
DROP FUNCTION IF EXISTS langconnect.backfill_public_permissions();

-- Update backfill_public_permissions to include skills
CREATE OR REPLACE FUNCTION langconnect.backfill_public_permissions()
RETURNS TABLE(graphs_granted INTEGER, assistants_granted INTEGER, collections_granted INTEGER, skills_granted INTEGER) AS $$
DECLARE
    graph_count INTEGER := 0;
    assistant_count INTEGER := 0;
    collection_count INTEGER := 0;
    skill_count INTEGER := 0;
BEGIN
    -- Grant all active public graph permissions to all existing users
    INSERT INTO langconnect.graph_permissions (user_id, graph_id, permission_level, granted_by)
    SELECT ur.user_id, pgp.graph_id, pgp.permission_level, 'system:public'
    FROM langconnect.user_roles ur
    CROSS JOIN langconnect.public_graph_permissions pgp
    WHERE pgp.revoked_at IS NULL
    ON CONFLICT (user_id, graph_id) DO NOTHING;

    GET DIAGNOSTICS graph_count = ROW_COUNT;

    -- Grant all active public assistant permissions to all existing users
    INSERT INTO langconnect.assistant_permissions (user_id, assistant_id, permission_level, granted_by)
    SELECT ur.user_id, pap.assistant_id::UUID, pap.permission_level, 'system:public'
    FROM langconnect.user_roles ur
    CROSS JOIN langconnect.public_assistant_permissions pap
    WHERE pap.revoked_at IS NULL
    ON CONFLICT (user_id, assistant_id) DO NOTHING;

    GET DIAGNOSTICS assistant_count = ROW_COUNT;

    -- Grant all active public collection permissions to all existing users
    INSERT INTO langconnect.collection_permissions (user_id, collection_id, permission_level, granted_by)
    SELECT ur.user_id, pcp.collection_id, pcp.permission_level, 'system:public'
    FROM langconnect.user_roles ur
    CROSS JOIN langconnect.public_collection_permissions pcp
    WHERE pcp.revoked_at IS NULL
    ON CONFLICT (collection_id, user_id) DO NOTHING;

    GET DIAGNOSTICS collection_count = ROW_COUNT;

    -- Grant all active public skill permissions to all existing users
    INSERT INTO langconnect.skill_permissions (user_id, skill_id, permission_level, granted_by)
    SELECT ur.user_id, psp.skill_id, psp.permission_level, 'system:public'
    FROM langconnect.user_roles ur
    CROSS JOIN langconnect.public_skill_permissions psp
    WHERE psp.revoked_at IS NULL
    ON CONFLICT (skill_id, user_id) DO NOTHING;

    GET DIAGNOSTICS skill_count = ROW_COUNT;

    RETURN QUERY SELECT graph_count, assistant_count, collection_count, skill_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STORAGE BUCKET FOR SKILLS
-- ============================================================================

-- Create the skills storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'skills',
    'skills',
    false,  -- Private bucket (requires authentication)
    104857600,  -- 100MB limit per skill zip
    ARRAY[
        'application/zip',
        'application/x-zip-compressed'
    ]::text[]
)
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

-- ============================================================================
-- STORAGE HELPER FUNCTION
-- ============================================================================

-- Helper function to check skill permissions for storage access
CREATE OR REPLACE FUNCTION storage.user_has_skill_permission(
    p_skill_uuid UUID,
    p_user_id UUID,
    p_min_permission TEXT DEFAULT 'viewer'
) RETURNS BOOLEAN AS $$
DECLARE
    v_permission_rank INTEGER;
    v_required_rank INTEGER;
    v_public_permission_level TEXT;
BEGIN
    -- Permission ranking
    v_required_rank := CASE p_min_permission
        WHEN 'viewer' THEN 1
        WHEN 'editor' THEN 2
        WHEN 'owner' THEN 3
        ELSE 0
    END;

    -- Check if skill has an active public permission
    SELECT permission_level INTO v_public_permission_level
    FROM langconnect.public_skill_permissions
    WHERE skill_id = p_skill_uuid AND revoked_at IS NULL;

    IF v_public_permission_level IS NOT NULL THEN
        -- Public permission exists - check if it meets minimum requirement
        v_permission_rank := CASE v_public_permission_level
            WHEN 'viewer' THEN 1
            WHEN 'editor' THEN 2
            ELSE 0
        END;
        IF v_permission_rank >= v_required_rank THEN
            RETURN TRUE;
        END IF;
    END IF;

    -- Check user's direct permission
    SELECT CASE permission_level
        WHEN 'viewer' THEN 1
        WHEN 'editor' THEN 2
        WHEN 'owner' THEN 3
        ELSE 0
    END INTO v_permission_rank
    FROM langconnect.skill_permissions
    WHERE skill_id = p_skill_uuid AND user_id = p_user_id::text;

    RETURN COALESCE(v_permission_rank >= v_required_rank, FALSE);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- STORAGE RLS POLICIES
-- ============================================================================

-- Policy: Allow users to upload to skills they can edit
DROP POLICY IF EXISTS "Users can upload to skills they can edit" ON storage.objects;
CREATE POLICY "Users can upload to skills they can edit"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'skills' AND
    storage.user_has_skill_permission(
        (storage.foldername(name))[1]::UUID,
        auth.uid(),
        'editor'
    )
);

-- Policy: Allow users to read skills they have access to
DROP POLICY IF EXISTS "Users can read accessible skills" ON storage.objects;
CREATE POLICY "Users can read accessible skills"
ON storage.objects
FOR SELECT
TO authenticated
USING (
    bucket_id = 'skills' AND
    storage.user_has_skill_permission(
        (storage.foldername(name))[1]::UUID,
        auth.uid(),
        'viewer'
    )
);

-- Policy: Allow users to update skills they can edit
DROP POLICY IF EXISTS "Users can update skills they can edit" ON storage.objects;
CREATE POLICY "Users can update skills they can edit"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
    bucket_id = 'skills' AND
    storage.user_has_skill_permission(
        (storage.foldername(name))[1]::UUID,
        auth.uid(),
        'editor'
    )
)
WITH CHECK (
    bucket_id = 'skills' AND
    storage.user_has_skill_permission(
        (storage.foldername(name))[1]::UUID,
        auth.uid(),
        'editor'
    )
);

-- Policy: Allow users to delete skills they own
DROP POLICY IF EXISTS "Users can delete skills they own" ON storage.objects;
CREATE POLICY "Users can delete skills they own"
ON storage.objects
FOR DELETE
TO authenticated
USING (
    bucket_id = 'skills' AND
    storage.user_has_skill_permission(
        (storage.foldername(name))[1]::UUID,
        auth.uid(),
        'owner'
    )
);

-- Policy: Service role has full access (for backend operations)
DROP POLICY IF EXISTS "Service role has full access to skills" ON storage.objects;
CREATE POLICY "Service role has full access to skills"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'skills')
WITH CHECK (bucket_id = 'skills');

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Updated_at trigger for skills table
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_skills_updated_at') THEN
    CREATE TRIGGER trigger_skills_updated_at
        BEFORE UPDATE ON langconnect.skills
        FOR EACH ROW
        EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

-- Updated_at trigger for skill_permissions table
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_skill_permissions_updated_at') THEN
    CREATE TRIGGER trigger_skill_permissions_updated_at
        BEFORE UPDATE ON langconnect.skill_permissions
        FOR EACH ROW
        EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

-- Updated_at trigger for public_skill_permissions table
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_public_skill_permissions_updated_at') THEN
    CREATE TRIGGER trigger_public_skill_permissions_updated_at
        BEFORE UPDATE ON langconnect.public_skill_permissions
        FOR EACH ROW
        EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

-- ============================================================================
-- GRANTS FOR AUTH ADMIN
-- ============================================================================

DO $$ BEGIN
  BEGIN
    GRANT SELECT, INSERT ON langconnect.skill_permissions TO supabase_auth_admin;
    GRANT SELECT ON langconnect.public_skill_permissions TO supabase_auth_admin;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
END $$;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE langconnect.skills IS 'Skills metadata table storing skill definitions and storage paths';
COMMENT ON COLUMN langconnect.skills.id IS 'Unique identifier for the skill';
COMMENT ON COLUMN langconnect.skills.name IS 'Skill name (lowercase, hyphens, numbers only, 1-64 chars)';
COMMENT ON COLUMN langconnect.skills.description IS 'Human-readable description of what the skill does (1-1024 chars)';
COMMENT ON COLUMN langconnect.skills.storage_path IS 'Path to the skill zip file in Supabase storage bucket';
COMMENT ON COLUMN langconnect.skills.pip_requirements IS 'Optional list of pip packages required by the skill';
COMMENT ON COLUMN langconnect.skills.created_by IS 'User ID of the skill creator';

COMMENT ON TABLE langconnect.skill_permissions IS 'Permissions controlling access to skills';
COMMENT ON COLUMN langconnect.skill_permissions.skill_id IS 'Reference to the skill';
COMMENT ON COLUMN langconnect.skill_permissions.user_id IS 'User ID who has permission';
COMMENT ON COLUMN langconnect.skill_permissions.permission_level IS 'Permission level: owner (full control), editor (can modify), viewer (read-only)';
COMMENT ON COLUMN langconnect.skill_permissions.granted_by IS 'User ID who granted this permission, or system:public for auto-granted';

COMMENT ON TABLE langconnect.public_skill_permissions IS 'Defines which skills are publicly available to all users';
COMMENT ON COLUMN langconnect.public_skill_permissions.skill_id IS 'The skill ID that should have public access';
COMMENT ON COLUMN langconnect.public_skill_permissions.permission_level IS 'Permission level granted to all users (viewer or editor)';
COMMENT ON COLUMN langconnect.public_skill_permissions.revoke_mode IS 'How to handle revocation: revoke_all removes all user permissions, future_only only affects new users';

COMMENT ON FUNCTION storage.user_has_skill_permission(UUID, UUID, TEXT) IS 'Check if a user has the required permission level for a skill (used by storage RLS policies)';

-- ============================================================================
-- RECORD MIGRATION
-- ============================================================================

INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('011', 'Create skills tables, storage bucket, and RLS policies')
ON CONFLICT (version) DO NOTHING;
