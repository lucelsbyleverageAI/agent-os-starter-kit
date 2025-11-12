-- Migration 007: Remove foreign key constraint to allow thread preservation
--
-- Background:
-- Migration 006 attempted to preserve assistant_id in threads after assistant deletion
-- by setting the FK constraint to ON DELETE NO ACTION. However, this blocks ALL deletions
-- when threads still reference the assistant, which defeats the purpose.
--
-- Solution:
-- Remove the foreign key constraint entirely. The application layer will handle thread
-- preservation through the is_deprecated flag. Threads are historical records that should
-- maintain their original context (assistant_id) even after the assistant is deleted.
--
-- This aligns with the frontend implementation which:
-- 1. Displays deprecated threads under "Archived Agents"
-- 2. Uses service account API to fetch messages for deprecated threads
-- 3. Shows threads in read-only mode when assistant is deleted

-- Drop the problematic foreign key constraint
ALTER TABLE langconnect.threads_mirror
DROP CONSTRAINT IF EXISTS fk_threads_mirror_assistant;

-- Add a comment documenting the intentional orphaning behavior
COMMENT ON COLUMN langconnect.threads_mirror.assistant_id IS
'Reference to the assistant that created this thread. May reference deleted assistants for deprecated threads. Use is_deprecated flag to identify orphaned threads.';

-- Note: The trigger mark_threads_deprecated_on_assistant_delete() from migration 005
-- will still fire and mark threads as deprecated when assistants are deleted.
-- This provides application-level tracking without database-level constraint enforcement.
