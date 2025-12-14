-- Migration 016: Create agent_run_costs table for per-run cost tracking
-- This table stores usage and cost data for each agent run, enabling:
-- - Cost breakdown by agent/assistant
-- - Cost breakdown by model
-- - Cost breakdown by user (admin view)
-- - Time-series cost analysis

SET search_path = langconnect, public;

-- Table: Agent Run Costs
-- Stores per-run cost and token usage data from OpenRouter
CREATE TABLE IF NOT EXISTS langconnect.agent_run_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Run identification
    thread_id UUID NOT NULL,
    run_id TEXT NOT NULL,

    -- Agent/Assistant identification
    assistant_id UUID,  -- Our agent instance ID (nullable for ad-hoc runs)
    graph_name TEXT,    -- Agent template name

    -- User identification
    user_id VARCHAR NOT NULL,

    -- Model information
    model_name TEXT NOT NULL,  -- e.g., 'anthropic/claude-sonnet-4.5'

    -- Token counts
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,

    -- Cost in credits (USD)
    cost DECIMAL(12, 8) NOT NULL DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign keys
    CONSTRAINT fk_agent_run_costs_user FOREIGN KEY (user_id)
        REFERENCES langconnect.user_roles(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_run_costs_thread FOREIGN KEY (thread_id)
        REFERENCES langconnect.threads_mirror(thread_id) ON DELETE CASCADE,

    -- Unique constraint: one cost entry per run
    UNIQUE(run_id)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_user_id
    ON langconnect.agent_run_costs(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_assistant_id
    ON langconnect.agent_run_costs(assistant_id) WHERE assistant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_thread_id
    ON langconnect.agent_run_costs(thread_id);
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_model_name
    ON langconnect.agent_run_costs(model_name);
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_created_at
    ON langconnect.agent_run_costs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_graph_name
    ON langconnect.agent_run_costs(graph_name) WHERE graph_name IS NOT NULL;

-- Composite index for date range queries with user filtering
CREATE INDEX IF NOT EXISTS idx_agent_run_costs_user_created
    ON langconnect.agent_run_costs(user_id, created_at DESC);

-- Comments for documentation
COMMENT ON TABLE langconnect.agent_run_costs IS
    'Per-run cost and token usage data from OpenRouter for detailed cost analysis';
COMMENT ON COLUMN langconnect.agent_run_costs.run_id IS
    'LangGraph run ID (unique identifier for each agent execution)';
COMMENT ON COLUMN langconnect.agent_run_costs.assistant_id IS
    'Our agent instance ID (UUID of the assistant that ran this execution)';
COMMENT ON COLUMN langconnect.agent_run_costs.graph_name IS
    'Agent template/graph name (e.g., tools_agent, deep_research_agent)';
COMMENT ON COLUMN langconnect.agent_run_costs.model_name IS
    'OpenRouter model ID used for this run (e.g., anthropic/claude-sonnet-4.5)';
COMMENT ON COLUMN langconnect.agent_run_costs.cost IS
    'Cost in USD credits (up to 8 decimal places for accurate micro-transactions)';
