-- Migration 008: Create feedback tables for agent and app feedback
-- This migration creates two tables:
-- 1. message_feedback: User feedback on AI messages with LangSmith integration
-- 2. app_feedback: General bug reports and feature requests

SET search_path = langconnect, public;

-- Create enum types for app feedback
CREATE TYPE langconnect.feedback_type AS ENUM ('bug', 'feature');
CREATE TYPE langconnect.feedback_status AS ENUM ('open', 'in_progress', 'resolved', 'closed');

-- Table 1: Message Feedback (Agent Chat Feedback)
-- Stores thumbs up/down feedback on AI responses with optional LangSmith sync
CREATE TABLE IF NOT EXISTS langconnect.message_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR NOT NULL,
    thread_id UUID NOT NULL,
    message_id VARCHAR NOT NULL,
    run_id VARCHAR,  -- LangSmith run ID (discovered via API correlation)
    score INTEGER NOT NULL CHECK (score IN (1, 0, -1)),  -- 1=thumbs up, -1=thumbs down, 0=removed
    category VARCHAR(50),  -- e.g., 'helpful', 'accurate', 'incorrect', 'incomplete'
    comment TEXT,
    langsmith_feedback_id UUID,  -- ID returned from LangSmith API
    langsmith_synced_at TIMESTAMPTZ,  -- When feedback was synced to LangSmith
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign keys
    CONSTRAINT fk_message_feedback_user FOREIGN KEY (user_id)
        REFERENCES langconnect.user_roles(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_message_feedback_thread FOREIGN KEY (thread_id)
        REFERENCES langconnect.threads_mirror(thread_id) ON DELETE CASCADE,

    -- One feedback per user per message
    UNIQUE(user_id, message_id)
);

-- Indexes for message_feedback
CREATE INDEX IF NOT EXISTS idx_message_feedback_user_id
    ON langconnect.message_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_thread_id
    ON langconnect.message_feedback(thread_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_message_id
    ON langconnect.message_feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_run_id
    ON langconnect.message_feedback(run_id) WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_message_feedback_created_at
    ON langconnect.message_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_message_feedback_score
    ON langconnect.message_feedback(score);

-- Updated_at trigger for message_feedback
CREATE TRIGGER trigger_message_feedback_updated_at
    BEFORE UPDATE ON langconnect.message_feedback
    FOR EACH ROW
    EXECUTE FUNCTION langconnect.update_updated_at_column();

-- Table 2: App Feedback (General Bug Reports & Feature Requests)
-- Stores general user feedback about the application
CREATE TABLE IF NOT EXISTS langconnect.app_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR NOT NULL,
    feedback_type langconnect.feedback_type NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    screenshot_urls TEXT[],  -- Array of storage bucket URLs
    page_url TEXT,  -- URL where feedback was submitted
    user_agent TEXT,  -- Browser user agent
    metadata JSONB DEFAULT '{}',  -- Additional context (viewport size, etc.)
    status langconnect.feedback_status NOT NULL DEFAULT 'open',
    admin_notes TEXT,  -- Admin notes for tracking resolution
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign keys
    CONSTRAINT fk_app_feedback_user FOREIGN KEY (user_id)
        REFERENCES langconnect.user_roles(user_id) ON DELETE CASCADE
);

-- Indexes for app_feedback
CREATE INDEX IF NOT EXISTS idx_app_feedback_user_id
    ON langconnect.app_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_app_feedback_type
    ON langconnect.app_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_app_feedback_status
    ON langconnect.app_feedback(status);
CREATE INDEX IF NOT EXISTS idx_app_feedback_created_at
    ON langconnect.app_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_feedback_type_status
    ON langconnect.app_feedback(feedback_type, status);

-- Updated_at trigger for app_feedback
CREATE TRIGGER trigger_app_feedback_updated_at
    BEFORE UPDATE ON langconnect.app_feedback
    FOR EACH ROW
    EXECUTE FUNCTION langconnect.update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE langconnect.message_feedback IS
    'User feedback on AI assistant messages with optional LangSmith integration';
COMMENT ON COLUMN langconnect.message_feedback.score IS
    '1 = thumbs up, -1 = thumbs down, 0 = feedback removed';
COMMENT ON COLUMN langconnect.message_feedback.run_id IS
    'LangSmith run ID discovered via API correlation with thread_id + timestamp';
COMMENT ON COLUMN langconnect.message_feedback.langsmith_feedback_id IS
    'UUID returned by LangSmith API when feedback is successfully synced';

COMMENT ON TABLE langconnect.app_feedback IS
    'General user feedback including bug reports and feature requests';
COMMENT ON COLUMN langconnect.app_feedback.feedback_type IS
    'Type of feedback: bug (issue report) or feature (enhancement request)';
COMMENT ON COLUMN langconnect.app_feedback.status IS
    'Current status: open, in_progress, resolved, or closed';
COMMENT ON COLUMN langconnect.app_feedback.screenshot_urls IS
    'Array of URLs pointing to uploaded screenshots in storage bucket';
