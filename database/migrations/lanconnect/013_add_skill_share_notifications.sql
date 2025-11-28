-- Add skill_share notification type and update accept_notification function
-- Idempotent and safe to re-run

-- ============================================================================
-- ADD skill_share TO notification_type ENUM
-- ============================================================================

-- Add skill_share to the notification_type enum if it doesn't exist
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'skill_share'
      AND enumtypid = 'langconnect.notification_type'::regtype
  ) THEN
    ALTER TYPE langconnect.notification_type ADD VALUE 'skill_share';
  END IF;
END $$;

-- ============================================================================
-- UPDATE resource_type CHECK CONSTRAINT TO INCLUDE 'skill'
-- ============================================================================

-- The notifications table has an inline CHECK constraint on resource_type
-- We need to drop and recreate it to include 'skill'
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    -- Find the constraint name for the resource_type check
    SELECT conname INTO constraint_name
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
    WHERE c.conrelid = 'langconnect.notifications'::regclass
      AND c.contype = 'c'  -- check constraint
      AND a.attname = 'resource_type';

    IF constraint_name IS NOT NULL THEN
        -- Drop the old constraint
        EXECUTE 'ALTER TABLE langconnect.notifications DROP CONSTRAINT ' || quote_ident(constraint_name);
    END IF;

    -- Add the new constraint with 'skill' included
    ALTER TABLE langconnect.notifications
    ADD CONSTRAINT notifications_resource_type_check
    CHECK (resource_type IN ('graph', 'assistant', 'collection', 'skill'));
END $$;

-- ============================================================================
-- UPDATE accept_notification FUNCTION TO HANDLE SKILLS
-- ============================================================================

-- Update the accept_notification function to handle skill resource type
CREATE OR REPLACE FUNCTION langconnect.accept_notification(p_notification_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    notification_record RECORD;
    success BOOLEAN := FALSE;
BEGIN
    -- Get notification details
    SELECT * INTO notification_record
    FROM langconnect.notifications
    WHERE id = p_notification_id AND status = 'pending';

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Grant permission based on resource type
    IF notification_record.resource_type = 'graph' THEN
        INSERT INTO langconnect.graph_permissions (graph_id, user_id, permission_level, granted_by)
        VALUES (notification_record.resource_id, notification_record.recipient_user_id::VARCHAR,
                notification_record.permission_level, notification_record.sender_user_id::VARCHAR)
        ON CONFLICT (graph_id, user_id) DO UPDATE SET
            permission_level = EXCLUDED.permission_level,
            granted_by = EXCLUDED.granted_by,
            updated_at = NOW();
        success := TRUE;
    ELSIF notification_record.resource_type = 'assistant' THEN
        INSERT INTO langconnect.assistant_permissions (assistant_id, user_id, permission_level, granted_by)
        VALUES (notification_record.resource_id::UUID, notification_record.recipient_user_id::VARCHAR,
                notification_record.permission_level, notification_record.sender_user_id::VARCHAR)
        ON CONFLICT (assistant_id, user_id) DO UPDATE SET
            permission_level = EXCLUDED.permission_level,
            granted_by = EXCLUDED.granted_by,
            updated_at = NOW();
        success := TRUE;
    ELSIF notification_record.resource_type = 'collection' THEN
        INSERT INTO langconnect.collection_permissions (collection_id, user_id, permission_level, granted_by)
        VALUES (notification_record.resource_id::UUID, notification_record.recipient_user_id::VARCHAR,
                notification_record.permission_level, notification_record.sender_user_id::VARCHAR)
        ON CONFLICT (collection_id, user_id) DO UPDATE SET
            permission_level = EXCLUDED.permission_level,
            granted_by = EXCLUDED.granted_by,
            updated_at = NOW();
        success := TRUE;
    ELSIF notification_record.resource_type = 'skill' THEN
        INSERT INTO langconnect.skill_permissions (skill_id, user_id, permission_level, granted_by)
        VALUES (notification_record.resource_id::UUID, notification_record.recipient_user_id::VARCHAR,
                notification_record.permission_level, notification_record.sender_user_id::VARCHAR)
        ON CONFLICT (skill_id, user_id) DO UPDATE SET
            permission_level = EXCLUDED.permission_level,
            granted_by = EXCLUDED.granted_by,
            updated_at = NOW();
        success := TRUE;
    END IF;

    -- Update notification status
    IF success THEN
        UPDATE langconnect.notifications
        SET status = 'accepted', responded_at = NOW()
        WHERE id = p_notification_id;
    END IF;

    RETURN success;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON FUNCTION langconnect.accept_notification(UUID) IS 'Accept a notification and grant the associated permission (supports graph, assistant, collection, and skill resources)';

-- ============================================================================
-- RECORD MIGRATION
-- ============================================================================

INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('013', 'Add skill_share notification type and update accept_notification function')
ON CONFLICT (version) DO NOTHING;
