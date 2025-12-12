-- Migration: Mark threads as read-only when assistant permissions are revoked
-- Purpose: Allow users to view past threads even after losing assistant access
-- Related Issue: https://github.com/lucelsbyleverageAI/agent-os-starter-kit/issues/142

-- Add index for efficient thread lookup during permission revocation
-- This partial index only includes non-deprecated threads (the common query pattern)
CREATE INDEX IF NOT EXISTS idx_threads_mirror_assistant_user_not_deprecated
ON langconnect.threads_mirror(assistant_id, user_id)
WHERE is_deprecated = FALSE;

-- Create function to mark threads as deprecated when permission is revoked
-- Uses SECURITY DEFINER to ensure proper privileges for thread updates
CREATE OR REPLACE FUNCTION langconnect.mark_threads_on_permission_revoke()
RETURNS TRIGGER AS $$
DECLARE
  assistant_name TEXT;
BEGIN
  -- Get assistant name for a meaningful deprecation reason
  SELECT name INTO assistant_name
  FROM langconnect.assistants_mirror
  WHERE assistant_id = OLD.assistant_id;

  -- Mark all threads belonging to this user for this assistant as deprecated
  -- This allows them to view past conversations in read-only mode
  UPDATE langconnect.threads_mirror
  SET
    is_deprecated = TRUE,
    deprecated_at = NOW(),
    deprecated_reason = 'Access to assistant "' || COALESCE(assistant_name, OLD.assistant_id::text) || '" was revoked'
  WHERE
    assistant_id = OLD.assistant_id
    AND user_id = OLD.user_id
    AND is_deprecated = FALSE;

  -- Increment threads cache version to notify frontends of the change
  PERFORM langconnect.increment_cache_version('threads');

  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger to run BEFORE permission deletion
-- This ensures threads are marked before the permission row is removed
DROP TRIGGER IF EXISTS trigger_deprecate_threads_on_permission_revoke ON langconnect.assistant_permissions;

CREATE TRIGGER trigger_deprecate_threads_on_permission_revoke
BEFORE DELETE ON langconnect.assistant_permissions
FOR EACH ROW
EXECUTE FUNCTION langconnect.mark_threads_on_permission_revoke();

-- Add documentation
COMMENT ON FUNCTION langconnect.mark_threads_on_permission_revoke() IS
'Marks user threads as deprecated when their assistant permission is revoked. This allows read-only viewing of past conversations through the "Archived Agents" filter in the chat history sidebar.';

-- Record this migration
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('015', 'Add trigger to mark threads as deprecated when assistant permissions are revoked')
ON CONFLICT (version) DO NOTHING;
