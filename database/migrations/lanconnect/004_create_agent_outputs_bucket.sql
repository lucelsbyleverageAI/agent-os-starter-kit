-- Create Supabase Storage bucket for agent-generated outputs (E2B sandbox, etc.)
-- Idempotent and safe to re-run

-- Create the agent-outputs storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'agent-outputs',
  'agent-outputs',
  false,  -- Private bucket (requires authentication)
  52428800,  -- 50MB limit (matching other buckets)
  ARRAY[
    -- Image formats
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff',
    'image/svg+xml',
    -- Data formats (for E2B outputs)
    'application/json',
    'text/html',
    'text/plain',
    'text/csv',
    'application/javascript',
    'text/x-latex'
  ]::text[]
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Create RLS policies for the agent-outputs bucket
-- Storage path format: {user_id}/{assistant_id}/{thread_id}/{timestamp}_{filename}
-- First folder in path is the user_id

-- Policy: Allow users to upload files to their own outputs
DROP POLICY IF EXISTS "Users can upload to their own agent outputs" ON storage.objects;
CREATE POLICY "Users can upload to their own agent outputs"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'agent-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow users to read files from their own outputs
DROP POLICY IF EXISTS "Users can read their own agent outputs" ON storage.objects;
CREATE POLICY "Users can read their own agent outputs"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'agent-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow users to update files in their own outputs
DROP POLICY IF EXISTS "Users can update their own agent outputs" ON storage.objects;
CREATE POLICY "Users can update their own agent outputs"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'agent-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::text
)
WITH CHECK (
  bucket_id = 'agent-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow users to delete files from their own outputs
DROP POLICY IF EXISTS "Users can delete their own agent outputs" ON storage.objects;
CREATE POLICY "Users can delete their own agent outputs"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'agent-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Service role has full access (for backend operations and cleanup)
DROP POLICY IF EXISTS "Service role has full access to agent outputs" ON storage.objects;
CREATE POLICY "Service role has full access to agent outputs"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'agent-outputs')
WITH CHECK (bucket_id = 'agent-outputs');

-- Record migration in tracking table
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('004', 'Create storage bucket and RLS policies for agent-generated outputs')
ON CONFLICT (version) DO NOTHING;
