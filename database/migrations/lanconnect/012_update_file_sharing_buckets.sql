-- Update storage buckets for Skills DeepAgent file sharing
-- 1. Update chat-uploads bucket to support documents (not just images)
-- 2. Update agent-outputs bucket to support more MIME types
-- Idempotent and safe to re-run

-- ============================================================================
-- UPDATE CHAT-UPLOADS BUCKET (User -> Agent uploads)
-- ============================================================================

-- Update the chat-uploads bucket to support document types
-- This allows users to upload Excel, Word, PDF, PowerPoint, CSV files
-- which are then transferred to the E2B sandbox for agent processing
UPDATE storage.buckets
SET allowed_mime_types = ARRAY[
    -- Images (existing)
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff',
    -- Documents (new)
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  -- .docx
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  -- .xlsx
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',  -- .pptx
    'application/msword',  -- .doc
    'application/vnd.ms-excel',  -- .xls
    'application/vnd.ms-powerpoint',  -- .ppt
    -- Text/Data (new)
    'text/plain',
    'text/csv',
    'text/markdown',
    'application/json'
]::text[]
WHERE id = 'chat-uploads';

-- ============================================================================
-- UPDATE AGENT-OUTPUTS BUCKET (Agent -> User outputs)
-- ============================================================================

-- Update the agent-outputs bucket to support more document types
-- This allows agents to publish various document types for user download
UPDATE storage.buckets
SET allowed_mime_types = ARRAY[
    -- Images
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff',
    'image/svg+xml',
    -- Documents
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  -- .docx
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  -- .xlsx
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',  -- .pptx
    'application/msword',  -- .doc
    'application/vnd.ms-excel',  -- .xls
    'application/vnd.ms-powerpoint',  -- .ppt
    -- Data formats
    'application/json',
    'text/html',
    'text/plain',
    'text/csv',
    'text/markdown',
    'application/javascript',
    'text/x-latex',
    'application/xml',
    -- Fallback
    'application/octet-stream'
]::text[]
WHERE id = 'agent-outputs';

-- ============================================================================
-- RECORD MIGRATION
-- ============================================================================

INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('012', 'Update chat-uploads and agent-outputs buckets to support documents for file sharing')
ON CONFLICT (version) DO NOTHING;
