-- Create Supabase Storage buckets for image and document uploads
-- Idempotent and safe to re-run

-- Create the collections storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'collections',
  'collections',
  false,  -- Private bucket (requires authentication)
  52428800,  -- 50MB limit (matching frontend validation)
  ARRAY[
    -- Image formats
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff',
    -- Document formats (for future use)
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'text/markdown'
  ]::text[]
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Helper function to check collection permissions for storage access
-- This function checks if a user has the required permission level for a collection
CREATE OR REPLACE FUNCTION storage.user_has_collection_permission(
  p_collection_uuid UUID,
  p_user_id UUID,
  p_min_permission TEXT DEFAULT 'viewer'
) RETURNS BOOLEAN AS $$
BEGIN
  -- Check if user has required permission level
  RETURN EXISTS (
    SELECT 1 FROM langconnect.collection_permissions
    WHERE collection_id = p_collection_uuid
    AND user_id = p_user_id::TEXT
    AND (
      (p_min_permission = 'viewer' AND permission_level IN ('viewer', 'editor', 'owner'))
      OR (p_min_permission = 'editor' AND permission_level IN ('editor', 'owner'))
      OR (p_min_permission = 'owner' AND permission_level = 'owner')
    )
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create RLS policies for the collections bucket (collection-based access)
-- Storage path format: {collection_uuid}/{timestamp}_{filename}
-- First folder in path is the collection_uuid

-- Policy: Allow users to upload files to collections they can edit
DROP POLICY IF EXISTS "Users can upload to collections they can edit" ON storage.objects;
CREATE POLICY "Users can upload to collections they can edit"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'collections' AND
  storage.user_has_collection_permission(
    (storage.foldername(name))[1]::UUID,
    auth.uid(),
    'editor'
  )
);

-- Policy: Allow users to read files in collections they have access to
DROP POLICY IF EXISTS "Users can read collection documents" ON storage.objects;
CREATE POLICY "Users can read collection documents"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'collections' AND
  storage.user_has_collection_permission(
    (storage.foldername(name))[1]::UUID,
    auth.uid(),
    'viewer'
  )
);

-- Policy: Allow users to update files in collections they can edit
DROP POLICY IF EXISTS "Users can update collection files" ON storage.objects;
CREATE POLICY "Users can update collection files"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'collections' AND
  storage.user_has_collection_permission(
    (storage.foldername(name))[1]::UUID,
    auth.uid(),
    'editor'
  )
)
WITH CHECK (
  bucket_id = 'collections' AND
  storage.user_has_collection_permission(
    (storage.foldername(name))[1]::UUID,
    auth.uid(),
    'editor'
  )
);

-- Policy: Allow users to delete files in collections they can edit
DROP POLICY IF EXISTS "Users can delete collection files" ON storage.objects;
CREATE POLICY "Users can delete collection files"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'collections' AND
  storage.user_has_collection_permission(
    (storage.foldername(name))[1]::UUID,
    auth.uid(),
    'editor'
  )
);

-- Policy: Service role has full access (for backend operations)
DROP POLICY IF EXISTS "Service role has full access to collections" ON storage.objects;
CREATE POLICY "Service role has full access to collections"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'collections')
WITH CHECK (bucket_id = 'collections');

-- Record migration in tracking table
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('002', 'Create storage buckets and RLS policies for image/document uploads')
ON CONFLICT (version) DO NOTHING;
