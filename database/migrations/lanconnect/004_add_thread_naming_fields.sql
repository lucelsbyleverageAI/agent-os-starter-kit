-- Migration: Add AI thread naming and summarization support
-- Description: Adds fields to threads_mirror for tracking message counts,
--              AI naming state, and user rename intent protection
-- Date: 2025-10-28

-- Add new columns to threads_mirror table
ALTER TABLE langconnect.threads_mirror
ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS needs_naming BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS last_naming_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS user_renamed BOOLEAN DEFAULT false;

-- Add comments for new columns
COMMENT ON COLUMN langconnect.threads_mirror.message_count IS 'Count of messages in thread for determining renaming intervals (1, 5, 10, 15...)';
COMMENT ON COLUMN langconnect.threads_mirror.needs_naming IS 'Flag indicating thread needs AI naming/summarization processing';
COMMENT ON COLUMN langconnect.threads_mirror.last_naming_at IS 'Timestamp of last AI naming operation to prevent redundant processing';
COMMENT ON COLUMN langconnect.threads_mirror.user_renamed IS 'Flag indicating user has manually renamed thread - protects from AI overwrites';

-- Create trigger function to automatically detect user renames
CREATE OR REPLACE FUNCTION langconnect.track_thread_rename()
RETURNS TRIGGER AS $$
BEGIN
    -- If name was changed by user (not by background AI job), mark as user-renamed
    -- We detect this by checking if name changed but last_naming_at didn't
    IF OLD.name IS DISTINCT FROM NEW.name
       AND (NEW.last_naming_at IS NULL OR NEW.last_naming_at = OLD.last_naming_at) THEN
        NEW.user_renamed := true;
        NEW.needs_naming := false;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on threads_mirror updates
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_track_thread_rename') THEN
    CREATE TRIGGER trigger_track_thread_rename
        BEFORE UPDATE ON langconnect.threads_mirror
        FOR EACH ROW
        EXECUTE FUNCTION langconnect.track_thread_rename();
  END IF;
END $$;

-- Add comment for the trigger function
COMMENT ON FUNCTION langconnect.track_thread_rename() IS 'Automatically detects user renames and sets protection flag to prevent AI overwrites';

-- Protect existing thread names by marking them as user-renamed
-- This is a safe default to avoid overwriting existing custom names during deployment
UPDATE langconnect.threads_mirror
SET user_renamed = true
WHERE name IS NOT NULL
  AND name != ''
  AND name != 'New Thread';  -- Exclude default placeholder names

-- Create index for efficient background job queries
CREATE INDEX IF NOT EXISTS idx_threads_mirror_needs_naming
ON langconnect.threads_mirror(needs_naming, user_renamed, last_naming_at)
WHERE needs_naming = true AND user_renamed = false;

-- Add comment for the index
COMMENT ON INDEX langconnect.idx_threads_mirror_needs_naming IS 'Optimizes background naming job queries for threads needing AI naming';

-- Record this migration
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('004', 'Add AI thread naming and summarization support')
ON CONFLICT (version) DO NOTHING;
