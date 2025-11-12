-- Migration: Add deprecated state for threads when assistants are deleted
-- Purpose: Allow users to view threads with deleted assistants in read-only mode

-- Add is_deprecated column to threads_mirror
ALTER TABLE langconnect.threads_mirror
ADD COLUMN IF NOT EXISTS is_deprecated BOOLEAN NOT NULL DEFAULT FALSE;

-- Add deprecated_at timestamp to track when thread was deprecated
ALTER TABLE langconnect.threads_mirror
ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ;

-- Add deprecated_reason to explain why thread was deprecated
ALTER TABLE langconnect.threads_mirror
ADD COLUMN IF NOT EXISTS deprecated_reason TEXT;

-- Create index for filtering deprecated threads
CREATE INDEX IF NOT EXISTS idx_threads_mirror_deprecated
ON langconnect.threads_mirror(is_deprecated)
WHERE is_deprecated = TRUE;

-- Create function to mark threads as deprecated when assistant is deleted
CREATE OR REPLACE FUNCTION langconnect.mark_threads_deprecated_on_assistant_delete()
RETURNS TRIGGER AS $$
BEGIN
  -- Mark all threads belonging to the deleted assistant as deprecated
  UPDATE langconnect.threads_mirror
  SET
    is_deprecated = TRUE,
    deprecated_at = NOW(),
    deprecated_reason = 'Assistant "' || OLD.name || '" (ID: ' || OLD.assistant_id || ') was deleted'
  WHERE
    assistant_id = OLD.assistant_id
    AND is_deprecated = FALSE; -- Only update if not already deprecated

  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically deprecate threads when assistant is deleted
DROP TRIGGER IF EXISTS trigger_deprecate_threads_on_assistant_delete ON langconnect.assistants_mirror;

CREATE TRIGGER trigger_deprecate_threads_on_assistant_delete
BEFORE DELETE ON langconnect.assistants_mirror
FOR EACH ROW
EXECUTE FUNCTION langconnect.mark_threads_deprecated_on_assistant_delete();

-- Backfill: Mark existing threads with NULL assistant_id as deprecated
-- This handles threads that were orphaned before this migration
UPDATE langconnect.threads_mirror
SET
  is_deprecated = TRUE,
  deprecated_at = NOW(),
  deprecated_reason = 'Assistant was previously deleted'
WHERE
  assistant_id IS NULL
  AND is_deprecated = FALSE;

-- Add comment for documentation
COMMENT ON COLUMN langconnect.threads_mirror.is_deprecated IS 'Indicates if the thread is deprecated due to assistant deletion. Deprecated threads are read-only.';
COMMENT ON COLUMN langconnect.threads_mirror.deprecated_at IS 'Timestamp when the thread was marked as deprecated.';
COMMENT ON COLUMN langconnect.threads_mirror.deprecated_reason IS 'Reason why the thread was deprecated (e.g., assistant deletion details).';
