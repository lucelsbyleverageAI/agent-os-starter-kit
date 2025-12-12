-- Migration: Add user deletion cascade trigger
-- Purpose: Clean up user_roles and associated permissions when auth.users is deleted
-- Related Issue: https://github.com/lucelsbyleverageAI/agent-os-starter-kit/issues/141

-- Create function to delete user role when auth user is deleted
-- This cascades to all permission tables via existing FK constraints
CREATE OR REPLACE FUNCTION langconnect.auto_delete_user_role()
RETURNS TRIGGER AS $$
BEGIN
  -- Mark all threads owned by this user as deprecated before deletion
  -- This preserves thread history for other users who may have interacted
  UPDATE langconnect.threads_mirror
  SET
    is_deprecated = TRUE,
    deprecated_at = NOW(),
    deprecated_reason = 'User account was deleted'
  WHERE user_id = OLD.id::text
    AND is_deprecated = FALSE;

  -- Delete user_roles entry - this cascades to all permission tables:
  -- - graph_permissions (ON DELETE CASCADE via fk_graph_permissions_user)
  -- - assistant_permissions (ON DELETE CASCADE via fk_assistant_permissions_user)
  -- - user_default_assistants (ON DELETE CASCADE via fk_user_default_user)
  DELETE FROM langconnect.user_roles
  WHERE user_id = OLD.id::text;

  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger to run before user deletion
DROP TRIGGER IF EXISTS trigger_auto_delete_user_role ON auth.users;

CREATE TRIGGER trigger_auto_delete_user_role
BEFORE DELETE ON auth.users
FOR EACH ROW
EXECUTE FUNCTION langconnect.auto_delete_user_role();

-- Grant necessary permissions to the auth admin role
DO $$ BEGIN
  BEGIN
    GRANT EXECUTE ON FUNCTION langconnect.auto_delete_user_role() TO supabase_auth_admin;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
END $$;

-- Add documentation
COMMENT ON FUNCTION langconnect.auto_delete_user_role() IS
'Automatically cleans up user_roles entry and marks threads as deprecated when a user is deleted from auth.users. Permission cleanup cascades automatically via FK constraints on graph_permissions, assistant_permissions, and user_default_assistants tables.';

-- Record this migration
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('014', 'Add user deletion cascade trigger for cleanup of user_roles and permissions')
ON CONFLICT (version) DO NOTHING;
