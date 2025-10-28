-- Create Supabase Storage bucket for E18 Process One-Pagers
-- Client-specific migration for E18 PowerPoint generation tool
-- Idempotent and safe to re-run

-- Create the process-one-pagers storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'process-one-pagers',
  'process-one-pagers',
  false,  -- Private bucket (requires authentication)
  52428800,  -- 50MB limit
  ARRAY[
    'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  ]::text[]
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Create RLS policies for the process-one-pagers bucket (user-based access)
-- Storage path format: {user_id}/generated_ppts/{timestamp}_{filename}
-- First folder in path is the user_id

-- Policy: Allow users to upload files to their own folder
DROP POLICY IF EXISTS "Users can upload their own process one-pagers" ON storage.objects;
CREATE POLICY "Users can upload their own process one-pagers"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'process-one-pagers' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Allow users to read their own files
DROP POLICY IF EXISTS "Users can read their own process one-pagers" ON storage.objects;
CREATE POLICY "Users can read their own process one-pagers"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'process-one-pagers' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Allow users to update their own files
DROP POLICY IF EXISTS "Users can update their own process one-pagers" ON storage.objects;
CREATE POLICY "Users can update their own process one-pagers"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'process-one-pagers' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
)
WITH CHECK (
  bucket_id = 'process-one-pagers' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Allow users to delete their own files
DROP POLICY IF EXISTS "Users can delete their own process one-pagers" ON storage.objects;
CREATE POLICY "Users can delete their own process one-pagers"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'process-one-pagers' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Service role has full access (for backend operations)
DROP POLICY IF EXISTS "Service role has full access to process one-pagers" ON storage.objects;
CREATE POLICY "Service role has full access to process one-pagers"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'process-one-pagers')
WITH CHECK (bucket_id = 'process-one-pagers');

-- Record migration in tracking table
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('C001', 'Create process-one-pagers bucket for E18 PowerPoint generation tool')
ON CONFLICT (version) DO NOTHING;
