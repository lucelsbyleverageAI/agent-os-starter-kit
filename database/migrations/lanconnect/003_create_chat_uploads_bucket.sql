-- Create Supabase Storage bucket for chat image uploads
-- Idempotent and safe to re-run

-- Create the chat-uploads storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'chat-uploads',
  'chat-uploads',
  false,  -- Private bucket (requires authentication)
  52428800,  -- 50MB limit (matching frontend validation)
  ARRAY[
    -- Image formats
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff'
  ]::text[]
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Create RLS policies for the chat-uploads bucket
-- Storage path format: {user_id}/{thread_id}/{timestamp}_{filename}
-- First folder in path is the user_id, second folder is thread_id

-- Policy: Allow users to upload files to their own threads
DROP POLICY IF EXISTS "Users can upload to their own threads" ON storage.objects;
CREATE POLICY "Users can upload to their own threads"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'chat-uploads' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow users to read files from their own threads
DROP POLICY IF EXISTS "Users can read their own chat uploads" ON storage.objects;
CREATE POLICY "Users can read their own chat uploads"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'chat-uploads' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow users to update files in their own threads
DROP POLICY IF EXISTS "Users can update their own chat uploads" ON storage.objects;
CREATE POLICY "Users can update their own chat uploads"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'chat-uploads' AND
  (storage.foldername(name))[1] = auth.uid()::text
)
WITH CHECK (
  bucket_id = 'chat-uploads' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow users to delete files from their own threads
DROP POLICY IF EXISTS "Users can delete their own chat uploads" ON storage.objects;
CREATE POLICY "Users can delete their own chat uploads"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'chat-uploads' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Service role has full access (for backend operations and cleanup)
DROP POLICY IF EXISTS "Service role has full access to chat uploads" ON storage.objects;
CREATE POLICY "Service role has full access to chat uploads"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'chat-uploads')
WITH CHECK (bucket_id = 'chat-uploads');

-- Record migration in tracking table
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('003', 'Create storage bucket and RLS policies for chat image uploads')
ON CONFLICT (version) DO NOTHING;
