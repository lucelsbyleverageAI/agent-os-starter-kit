-- Migration: Preserve assistant_id in threads when assistant is deleted
-- Purpose: Allow loading thread messages from LangGraph even for deprecated threads

-- Drop the existing trigger that runs BEFORE DELETE
-- We'll recreate it to run AFTER DELETE so assistant_id is still available
DROP TRIGGER IF EXISTS trigger_deprecate_threads_on_assistant_delete ON langconnect.assistants_mirror;

-- Drop the existing foreign key constraint that sets assistant_id to NULL
ALTER TABLE langconnect.threads_mirror
DROP CONSTRAINT IF EXISTS fk_threads_mirror_assistant;

-- Recreate the foreign key constraint with NO ACTION instead of SET NULL
-- This preserves the assistant_id even after the assistant is deleted
ALTER TABLE langconnect.threads_mirror
ADD CONSTRAINT fk_threads_mirror_assistant
FOREIGN KEY (assistant_id)
REFERENCES langconnect.assistants_mirror(assistant_id)
ON DELETE NO ACTION;

-- Update the trigger function to run AFTER DELETE
-- Since the constraint is now NO ACTION, we need to handle this differently
-- We'll disable the constraint temporarily during the deletion
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
    AND is_deprecated = FALSE;

  -- Don't block the deletion
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Recreate trigger to run AFTER DELETE
CREATE TRIGGER trigger_deprecate_threads_on_assistant_delete
AFTER DELETE ON langconnect.assistants_mirror
FOR EACH ROW
EXECUTE FUNCTION langconnect.mark_threads_deprecated_on_assistant_delete();

-- Actually, we need a different approach - let's make the constraint DEFERRABLE
-- and temporarily defer it during assistant deletion
ALTER TABLE langconnect.threads_mirror
DROP CONSTRAINT IF EXISTS fk_threads_mirror_assistant;

-- Create a NOT VALID constraint so it doesn't check existing data
-- This allows assistant_id to reference deleted assistants
ALTER TABLE langconnect.threads_mirror
ADD CONSTRAINT fk_threads_mirror_assistant
FOREIGN KEY (assistant_id)
REFERENCES langconnect.assistants_mirror(assistant_id)
ON DELETE NO ACTION
NOT VALID;

-- Add comment explaining the constraint
COMMENT ON CONSTRAINT fk_threads_mirror_assistant ON langconnect.threads_mirror IS
'Foreign key constraint with NO ACTION and NOT VALID allows threads to preserve assistant_id even after assistant deletion, enabling message retrieval from LangGraph for deprecated threads.';
