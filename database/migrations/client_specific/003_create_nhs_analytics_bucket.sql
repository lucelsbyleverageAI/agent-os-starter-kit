-- Create Supabase Storage bucket for NHS Analytics outputs
-- Client-specific migration for NHS performance data analysis toolkit
-- Idempotent and safe to re-run

-- Create the nhs-analytics-outputs storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'nhs-analytics-outputs',
  'nhs-analytics-outputs',
  false,  -- Private bucket (requires authentication)
  104857600,  -- 100MB limit
  ARRAY[
    'image/png',
    'image/svg+xml',
    'application/pdf',
    'text/csv',
    'application/json'
  ]::text[]
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Create RLS policies for the nhs-analytics-outputs bucket (user-based access)
-- Storage path format: {user_id}/{timestamp}_{filename}
-- First folder in path is the user_id

-- Policy: Allow users to upload files to their own folder
DROP POLICY IF EXISTS "Users can upload their own NHS analytics outputs" ON storage.objects;
CREATE POLICY "Users can upload their own NHS analytics outputs"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'nhs-analytics-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Allow users to read their own files
DROP POLICY IF EXISTS "Users can read their own NHS analytics outputs" ON storage.objects;
CREATE POLICY "Users can read their own NHS analytics outputs"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'nhs-analytics-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Allow users to update their own files
DROP POLICY IF EXISTS "Users can update their own NHS analytics outputs" ON storage.objects;
CREATE POLICY "Users can update their own NHS analytics outputs"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'nhs-analytics-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
)
WITH CHECK (
  bucket_id = 'nhs-analytics-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Allow users to delete their own files
DROP POLICY IF EXISTS "Users can delete their own NHS analytics outputs" ON storage.objects;
CREATE POLICY "Users can delete their own NHS analytics outputs"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'nhs-analytics-outputs' AND
  (storage.foldername(name))[1] = auth.uid()::TEXT
);

-- Policy: Service role has full access (for backend operations)
DROP POLICY IF EXISTS "Service role has full access to NHS analytics outputs" ON storage.objects;
CREATE POLICY "Service role has full access to NHS analytics outputs"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'nhs-analytics-outputs')
WITH CHECK (bucket_id = 'nhs-analytics-outputs');

-- Record migration in tracking table
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('C003', 'Create nhs-analytics-outputs bucket for NHS performance data analysis toolkit')
ON CONFLICT (version) DO NOTHING;
