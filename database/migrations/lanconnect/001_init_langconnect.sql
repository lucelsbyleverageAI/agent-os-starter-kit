-- Consolidated LAN Connect baseline schema (squashed)
-- Idempotent and safe to re-run

-- Ensure extensions and schema
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS langconnect;
SET search_path = langconnect, public;

-- Create all enums first
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type 
    WHERE typname = 'notification_status' 
      AND typnamespace = 'langconnect'::regnamespace
  ) THEN
    CREATE TYPE langconnect.notification_status AS ENUM (
      'pending',
      'accepted', 
      'rejected',
      'expired'
    );
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type 
    WHERE typname = 'notification_type' 
      AND typnamespace = 'langconnect'::regnamespace
  ) THEN
    CREATE TYPE langconnect.notification_type AS ENUM (
      'graph_share',
      'assistant_share',
      'collection_share'
    );
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type 
    WHERE typname = 'job_status' 
      AND typnamespace = 'langconnect'::regnamespace
  ) THEN
    CREATE TYPE langconnect.job_status AS ENUM (
      'pending',
      'processing',
      'completed',
      'failed',
      'cancelled'
    );
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type 
    WHERE typname = 'job_type' 
      AND typnamespace = 'langconnect'::regnamespace
  ) THEN
    CREATE TYPE langconnect.job_type AS ENUM (
      'document_processing',
      'youtube_processing',
      'url_processing',
      'text_processing',
      'reprocess_document'
    );
  END IF;
END $$;

-- LangChain core tables (create first as they are referenced by other tables)
CREATE TABLE IF NOT EXISTS langconnect.langchain_pg_collection (
  uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  cmetadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert special system collection for text extraction (chat feature)
-- This collection is used for TEXT_PROCESSING jobs that extract text for immediate use
-- in chat messages, rather than saving to a knowledge base collection
INSERT INTO langconnect.langchain_pg_collection (uuid, name, cmetadata, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::UUID,
    '_system_text_extraction',
    '{"description": "Special system collection for text extraction jobs (chat feature)", "is_system": true, "purpose": "text_extraction"}'::JSONB,
    NOW(),
    NOW()
)
ON CONFLICT (uuid) DO NOTHING;

CREATE TABLE IF NOT EXISTS langconnect.langchain_pg_document (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id UUID NOT NULL,
  content TEXT NOT NULL,
  cmetadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT fk_document_collection FOREIGN KEY (collection_id) REFERENCES langconnect.langchain_pg_collection(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS langconnect.langchain_pg_embedding (
  id TEXT PRIMARY KEY,
  collection_id UUID NOT NULL,
  document_id UUID NULL,
  document TEXT NOT NULL,
  embedding vector NOT NULL,
  cmetadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT fk_embedding_collection FOREIGN KEY (collection_id) REFERENCES langconnect.langchain_pg_collection(uuid) ON DELETE CASCADE,
  CONSTRAINT fk_embedding_document FOREIGN KEY (document_id) REFERENCES langconnect.langchain_pg_document(id) ON DELETE CASCADE
);

-- Collection permission tables (after LangChain tables for FK dependencies)
CREATE TABLE IF NOT EXISTS langconnect.collection_permissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id UUID NOT NULL,
  user_id VARCHAR NOT NULL,
  permission_level VARCHAR NOT NULL CHECK (permission_level IN ('owner','editor','viewer')),
  granted_by VARCHAR NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(collection_id, user_id),
  CONSTRAINT fk_collection_permissions_collection FOREIGN KEY (collection_id)
    REFERENCES langconnect.langchain_pg_collection(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS langconnect.public_collection_permissions (
  id SERIAL PRIMARY KEY,
  collection_id UUID NOT NULL,
  permission_level TEXT NOT NULL DEFAULT 'viewer',
  created_by UUID NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  revoked_at TIMESTAMP WITH TIME ZONE,
  revoke_mode TEXT CHECK (revoke_mode IN ('revoke_all','future_only')),
  notes TEXT,
  CONSTRAINT valid_collection_permission_level CHECK (permission_level IN ('viewer','editor','owner')),
  CONSTRAINT valid_collection_revoke_state CHECK ((revoked_at IS NULL AND revoke_mode IS NULL) OR (revoked_at IS NOT NULL AND revoke_mode IS NOT NULL)),
  CONSTRAINT unique_active_collection_permission EXCLUDE (collection_id WITH =) WHERE (revoked_at IS NULL)
);

-- Processing jobs table (for realtime) - after LangChain tables for FK dependencies
CREATE TABLE IF NOT EXISTS langconnect.processing_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id VARCHAR NOT NULL,
  collection_id UUID NOT NULL,
  job_type langconnect.job_type NOT NULL,
  status langconnect.job_status NOT NULL DEFAULT 'pending',
  title VARCHAR NOT NULL,
  description TEXT,
  processing_options JSONB DEFAULT '{}',
  progress_percent INTEGER DEFAULT 0 CHECK (progress_percent >= 0 AND progress_percent <= 100),
  current_step VARCHAR,
  total_steps INTEGER,
  input_data JSONB NOT NULL,
  result_data JSONB,
  error_message TEXT,
  error_details JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  processing_time_seconds INTEGER,
  documents_processed INTEGER DEFAULT 0,
  chunks_created INTEGER DEFAULT 0,
  CONSTRAINT valid_progress CHECK (
    (status = 'pending' AND progress_percent = 0) OR
    (status = 'processing' AND progress_percent >= 0 AND progress_percent < 100) OR
    (status IN ('completed','failed','cancelled') AND progress_percent <= 100)
  ),
  CONSTRAINT fk_processing_jobs_collection FOREIGN KEY (collection_id) REFERENCES langconnect.langchain_pg_collection(uuid) ON DELETE CASCADE
);

-- Migration tracking tables (two tracks)
CREATE TABLE IF NOT EXISTS langconnect.lanconnect_migration_versions (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'applied', -- 'applied' | 'failed'
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_lc_migrations_applied_at ON langconnect.lanconnect_migration_versions(applied_at);
CREATE INDEX IF NOT EXISTS idx_lc_migrations_status ON langconnect.lanconnect_migration_versions(status);

CREATE TABLE IF NOT EXISTS langconnect.client_migration_versions (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'applied', -- 'applied' | 'failed'
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_client_migrations_applied_at ON langconnect.client_migration_versions(applied_at);
CREATE INDEX IF NOT EXISTS idx_client_migrations_status ON langconnect.client_migration_versions(status);

-- Utility updated_at trigger function
CREATE OR REPLACE FUNCTION langconnect.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

-- Core permission tables (final types)
CREATE TABLE IF NOT EXISTS langconnect.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id VARCHAR NOT NULL UNIQUE,
  role VARCHAR NOT NULL CHECK (role IN ('dev_admin','business_admin','user')),
  email VARCHAR,
  display_name VARCHAR,
  assigned_by VARCHAR,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS langconnect.graph_permissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  graph_id TEXT NOT NULL,
  user_id VARCHAR NOT NULL,
  permission_level VARCHAR NOT NULL CHECK (permission_level IN ('admin','access')),
  granted_by VARCHAR NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(graph_id, user_id)
);

CREATE TABLE IF NOT EXISTS langconnect.assistant_permissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assistant_id UUID NOT NULL,
  user_id VARCHAR NOT NULL,
  permission_level VARCHAR NOT NULL CHECK (permission_level IN ('owner','editor','viewer')),
  granted_by VARCHAR NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(assistant_id, user_id)
);

-- Public permissions
CREATE TABLE IF NOT EXISTS langconnect.public_graph_permissions (
  id SERIAL PRIMARY KEY,
  graph_id TEXT NOT NULL,
  permission_level TEXT NOT NULL DEFAULT 'access',
  created_by UUID NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  revoked_at TIMESTAMP WITH TIME ZONE,
  revoke_mode TEXT CHECK (revoke_mode IN ('revoke_all','future_only')),
  notes TEXT,
  CONSTRAINT valid_permission_level CHECK (permission_level IN ('access','admin')),
  CONSTRAINT valid_revoke_state CHECK ((revoked_at IS NULL AND revoke_mode IS NULL) OR (revoked_at IS NOT NULL AND revoke_mode IS NOT NULL)),
  CONSTRAINT unique_active_graph_permission EXCLUDE (graph_id WITH =) WHERE (revoked_at IS NULL)
);

CREATE TABLE IF NOT EXISTS langconnect.public_assistant_permissions (
  id SERIAL PRIMARY KEY,
  assistant_id TEXT NOT NULL,
  permission_level TEXT NOT NULL DEFAULT 'viewer',
  created_by UUID NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  revoked_at TIMESTAMP WITH TIME ZONE,
  revoke_mode TEXT CHECK (revoke_mode IN ('revoke_all','future_only')),
  notes TEXT,
  CONSTRAINT valid_assistant_permission_level CHECK (permission_level IN ('viewer','editor','owner')),
  CONSTRAINT valid_assistant_revoke_state CHECK ((revoked_at IS NULL AND revoke_mode IS NULL) OR (revoked_at IS NOT NULL AND revoke_mode IS NOT NULL)),
  CONSTRAINT unique_active_assistant_permission EXCLUDE (assistant_id WITH =) WHERE (revoked_at IS NULL)
);



-- Mirror tables
CREATE TABLE IF NOT EXISTS langconnect.graphs_mirror (
  graph_id TEXT PRIMARY KEY,
  assistants_count INTEGER NOT NULL DEFAULT 0,
  has_default_assistant BOOLEAN NOT NULL DEFAULT FALSE,
  -- Human-facing presentation fields (editable by admins)
  name TEXT,
  description TEXT,
  schema_accessible BOOLEAN NOT NULL DEFAULT FALSE,
  langgraph_first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  langgraph_last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  mirror_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  langgraph_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dev baseline: backfill default names from graph_id where missing
DO $$ BEGIN
  BEGIN
    UPDATE langconnect.graphs_mirror
    SET name = initcap(replace(graph_id, '_', ' '))
    WHERE name IS NULL;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
END $$;

CREATE TABLE IF NOT EXISTS langconnect.assistants_mirror (
  assistant_id UUID PRIMARY KEY,
  graph_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  tags TEXT[] DEFAULT '{}',
  config JSONB NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}',
  context JSONB NOT NULL DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1,
  langgraph_created_at TIMESTAMPTZ NOT NULL,
  langgraph_updated_at TIMESTAMPTZ NOT NULL,
  mirror_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  langgraph_hash TEXT,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_assistants_mirror_graph FOREIGN KEY (graph_id) REFERENCES langconnect.graphs_mirror(graph_id) ON DELETE CASCADE
);

-- User default assistants table for chat auto-selection
CREATE TABLE IF NOT EXISTS langconnect.user_default_assistants (
  user_id VARCHAR PRIMARY KEY,
  assistant_id UUID NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT fk_user_default_user FOREIGN KEY (user_id)
    REFERENCES langconnect.user_roles(user_id) ON DELETE CASCADE,
  CONSTRAINT fk_user_default_assistant FOREIGN KEY (assistant_id)
    REFERENCES langconnect.assistants_mirror(assistant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_default_assistants_assistant
  ON langconnect.user_default_assistants(assistant_id);

CREATE TABLE IF NOT EXISTS langconnect.assistant_schemas (
  assistant_id UUID PRIMARY KEY,
  input_schema JSONB,
  config_schema JSONB,
  state_schema JSONB,
  schema_etag TEXT,
  last_fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_assistant_schemas_assistant FOREIGN KEY (assistant_id) REFERENCES langconnect.assistants_mirror(assistant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS langconnect.graph_schemas (
  graph_id TEXT PRIMARY KEY,
  input_schema JSONB,
  config_schema JSONB,
  state_schema JSONB,
  schema_etag TEXT,
  last_fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_graph_schemas_graph FOREIGN KEY (graph_id) REFERENCES langconnect.graphs_mirror(graph_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS langconnect.threads_mirror (
  thread_id UUID PRIMARY KEY,
  assistant_id UUID,
  graph_id TEXT,
  user_id TEXT,
  name TEXT,
  summary TEXT,
  status TEXT,
  last_message_at TIMESTAMPTZ,
  langgraph_created_at TIMESTAMPTZ NOT NULL,
  langgraph_updated_at TIMESTAMPTZ,
  mirror_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_threads_mirror_assistant FOREIGN KEY (assistant_id) REFERENCES langconnect.assistants_mirror(assistant_id) ON DELETE SET NULL,
  CONSTRAINT fk_threads_mirror_graph FOREIGN KEY (graph_id) REFERENCES langconnect.graphs_mirror(graph_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS langconnect.cache_state (
  id INTEGER PRIMARY KEY DEFAULT 1,
  graphs_version BIGINT NOT NULL DEFAULT 1,
  assistants_version BIGINT NOT NULL DEFAULT 1,
  schemas_version BIGINT NOT NULL DEFAULT 1,
  graph_schemas_version BIGINT NOT NULL DEFAULT 1,
  threads_version BIGINT NOT NULL DEFAULT 1,
  last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT single_cache_state_row CHECK (id = 1)
);
INSERT INTO langconnect.cache_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Mirroring functions (from archived migrations)
-- Compute stable hash of assistant fields for change detection
CREATE OR REPLACE FUNCTION langconnect.compute_assistant_hash(
    assistant_name TEXT,
    assistant_config JSONB,
    assistant_metadata JSONB,
    assistant_context JSONB,
    assistant_version INTEGER,
    lg_created_at TIMESTAMPTZ,
    lg_updated_at TIMESTAMPTZ
) RETURNS TEXT AS $$
BEGIN
    BEGIN
        RETURN encode(
            digest(
                COALESCE(assistant_name, '') || 
                COALESCE(assistant_config::text, '{}') ||
                COALESCE(assistant_metadata::text, '{}') ||
                COALESCE(assistant_context::text, '{}') ||
                COALESCE(assistant_version::text, '1') ||
                COALESCE(extract(epoch from lg_created_at)::text, '0') ||
                COALESCE(extract(epoch from lg_updated_at)::text, '0'),
                'sha256'
            ),
            'hex'
        );
    EXCEPTION WHEN undefined_function THEN
        RETURN hashtext(
            COALESCE(assistant_name, '') || 
            COALESCE(assistant_config::text, '{}') ||
            COALESCE(assistant_metadata::text, '{}') ||
            COALESCE(assistant_context::text, '{}') ||
            COALESCE(assistant_version::text, '1') ||
            COALESCE(extract(epoch from lg_created_at)::text, '0') ||
            COALESCE(extract(epoch from lg_updated_at)::text, '0')
        )::text;
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Compute graph-level hash from aggregated assistant hashes
CREATE OR REPLACE FUNCTION langconnect.compute_graph_hash(
    target_graph_id TEXT
) RETURNS TEXT AS $$
DECLARE
    assistant_data TEXT;
BEGIN
    SELECT string_agg(langgraph_hash, '|' ORDER BY assistant_id)
    INTO assistant_data
    FROM langconnect.assistants_mirror
    WHERE graph_id = target_graph_id;
    
    IF assistant_data IS NULL THEN
        RETURN '';
    END IF;
    
    BEGIN
        RETURN encode(digest(assistant_data, 'sha256'), 'hex');
    EXCEPTION WHEN undefined_function THEN
        RETURN hashtext(assistant_data)::text;
    END;
END;
$$ LANGUAGE plpgsql;

-- Atomically increment cache version for frontend invalidation
CREATE OR REPLACE FUNCTION langconnect.increment_cache_version(
    version_type TEXT
) RETURNS BIGINT AS $$
DECLARE
    new_version BIGINT;
BEGIN
    UPDATE langconnect.cache_state
    SET
        graphs_version = CASE WHEN version_type = 'graphs' THEN graphs_version + 1 ELSE graphs_version END,
        assistants_version = CASE WHEN version_type = 'assistants' THEN assistants_version + 1 ELSE assistants_version END,
        schemas_version = CASE WHEN version_type = 'schemas' THEN schemas_version + 1 ELSE schemas_version END,
        graph_schemas_version = CASE WHEN version_type = 'graph_schemas' THEN graph_schemas_version + 1 ELSE graph_schemas_version END,
        threads_version = CASE WHEN version_type = 'threads' THEN threads_version + 1 ELSE threads_version END,
        updated_at = NOW()
    WHERE id = 1;

    SELECT
        CASE
            WHEN version_type = 'graphs' THEN graphs_version
            WHEN version_type = 'assistants' THEN assistants_version
            WHEN version_type = 'schemas' THEN schemas_version
            WHEN version_type = 'graph_schemas' THEN graph_schemas_version
            WHEN version_type = 'threads' THEN threads_version
            ELSE 0
        END
    INTO new_version
    FROM langconnect.cache_state
    WHERE id = 1;

    RETURN new_version;
END;
$$ LANGUAGE plpgsql;

-- Upsert assistant into mirror with change detection and version increment
CREATE OR REPLACE FUNCTION langconnect.upsert_assistant_mirror(
    p_assistant_id UUID,
    p_graph_id TEXT,
    p_name TEXT,
    p_config JSONB,
    p_metadata JSONB,
    p_context JSONB,
    p_version INTEGER,
    p_langgraph_created_at TIMESTAMPTZ,
    p_langgraph_updated_at TIMESTAMPTZ
) RETURNS BOOLEAN AS $$
DECLARE
    new_hash TEXT;
    existing_hash TEXT;
    version_incremented BOOLEAN := FALSE;
BEGIN
    new_hash := langconnect.compute_assistant_hash(
        p_name, p_config, p_metadata, p_context, p_version,
        p_langgraph_created_at, p_langgraph_updated_at
    );
    
    SELECT langgraph_hash INTO existing_hash
    FROM langconnect.assistants_mirror
    WHERE assistant_id = p_assistant_id;
    
    IF existing_hash IS NULL OR existing_hash != new_hash THEN
        INSERT INTO langconnect.graphs_mirror (graph_id, name)
        VALUES (p_graph_id, initcap(replace(p_graph_id, '_', ' ')))
        ON CONFLICT (graph_id) DO NOTHING;
        -- Fill default name if row existed already without a name
        UPDATE langconnect.graphs_mirror
        SET name = COALESCE(name, initcap(replace(p_graph_id, '_', ' ')))
        WHERE graph_id = p_graph_id;
        
        INSERT INTO langconnect.assistants_mirror (
            assistant_id, graph_id, name, config, metadata, context, version,
            langgraph_created_at, langgraph_updated_at, langgraph_hash, last_seen_at
        ) VALUES (
            p_assistant_id, p_graph_id, p_name, p_config, p_metadata, p_context, p_version,
            p_langgraph_created_at, p_langgraph_updated_at, new_hash, NOW()
        )
        ON CONFLICT (assistant_id) DO UPDATE SET
            graph_id = EXCLUDED.graph_id,
            name = EXCLUDED.name,
            config = EXCLUDED.config,
            metadata = EXCLUDED.metadata,
            context = EXCLUDED.context,
            version = EXCLUDED.version,
            langgraph_created_at = EXCLUDED.langgraph_created_at,
            langgraph_updated_at = EXCLUDED.langgraph_updated_at,
            langgraph_hash = EXCLUDED.langgraph_hash,
            last_seen_at = EXCLUDED.last_seen_at,
            mirror_updated_at = NOW(),
            updated_at = NOW();
        
        PERFORM langconnect.increment_cache_version('assistants');
        version_incremented := TRUE;
    ELSE
        UPDATE langconnect.assistants_mirror
        SET last_seen_at = NOW()
        WHERE assistant_id = p_assistant_id;
    END IF;
    
    RETURN version_incremented;
END;
$$ LANGUAGE plpgsql;

-- Refresh graph aggregations and increment version if changed
CREATE OR REPLACE FUNCTION langconnect.refresh_graph_mirror(
    p_graph_id TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    assistant_count INTEGER;
    has_default BOOLEAN;
    schema_accessible BOOLEAN;
    new_graph_hash TEXT;
    existing_graph_hash TEXT;
    version_incremented BOOLEAN := FALSE;
BEGIN
    SELECT 
        COUNT(*),
        COUNT(*) FILTER (WHERE metadata->>'created_by' = 'system' OR metadata->>'_x_oap_is_default' = 'true') > 0,
        COALESCE(bool_or(CASE WHEN metadata->>'created_by' = 'system' THEN TRUE ELSE NULL END), FALSE)
    INTO assistant_count, has_default, schema_accessible
    FROM langconnect.assistants_mirror
    WHERE graph_id = p_graph_id;
    
    new_graph_hash := langconnect.compute_graph_hash(p_graph_id);
    
    SELECT langgraph_hash INTO existing_graph_hash
    FROM langconnect.graphs_mirror
    WHERE graph_id = p_graph_id;
    
    IF existing_graph_hash IS NULL OR existing_graph_hash != new_graph_hash THEN
        INSERT INTO langconnect.graphs_mirror (
            graph_id, assistants_count, has_default_assistant, schema_accessible,
            name,
            langgraph_hash, langgraph_last_seen_at
        ) VALUES (
            p_graph_id, assistant_count, has_default, schema_accessible,
            initcap(replace(p_graph_id, '_', ' ')),
            new_graph_hash, NOW()
        )
        ON CONFLICT (graph_id) DO UPDATE SET
            assistants_count = EXCLUDED.assistants_count,
            has_default_assistant = EXCLUDED.has_default_assistant,
            schema_accessible = EXCLUDED.schema_accessible,
            name = COALESCE(langconnect.graphs_mirror.name, EXCLUDED.name),
            langgraph_hash = EXCLUDED.langgraph_hash,
            langgraph_last_seen_at = EXCLUDED.langgraph_last_seen_at,
            mirror_updated_at = NOW(),
            updated_at = NOW();
        
        PERFORM langconnect.increment_cache_version('graphs');
        version_incremented := TRUE;
    ELSE
        UPDATE langconnect.graphs_mirror
        SET langgraph_last_seen_at = NOW()
        WHERE graph_id = p_graph_id;
    END IF;
    
    RETURN version_incremented;
END;
$$ LANGUAGE plpgsql;

-- Upsert assistant schemas with change detection and version increment
CREATE OR REPLACE FUNCTION langconnect.upsert_assistant_schemas(
    p_assistant_id UUID,
    p_input_schema JSONB,
    p_config_schema JSONB,
    p_state_schema JSONB
) RETURNS BOOLEAN AS $$
DECLARE
    new_etag TEXT;
    existing_etag TEXT;
    version_incremented BOOLEAN := FALSE;
BEGIN
    BEGIN
        new_etag := encode(
            digest(
                COALESCE(p_input_schema::text, 'null') ||
                COALESCE(p_config_schema::text, 'null') ||
                COALESCE(p_state_schema::text, 'null'),
                'sha256'
            ),
            'hex'
        );
    EXCEPTION WHEN undefined_function THEN
        new_etag := hashtext(
            COALESCE(p_input_schema::text, 'null') ||
            COALESCE(p_config_schema::text, 'null') ||
            COALESCE(p_state_schema::text, 'null')
        )::text;
    END;

    SELECT schema_etag INTO existing_etag
    FROM langconnect.assistant_schemas
    WHERE assistant_id = p_assistant_id;

    IF existing_etag IS NULL OR existing_etag != new_etag THEN
        INSERT INTO langconnect.assistant_schemas (
            assistant_id, input_schema, config_schema, state_schema,
            schema_etag, last_fetched_at
        ) VALUES (
            p_assistant_id, p_input_schema, p_config_schema, p_state_schema,
            new_etag, NOW()
        )
        ON CONFLICT (assistant_id) DO UPDATE SET
            input_schema = EXCLUDED.input_schema,
            config_schema = EXCLUDED.config_schema,
            state_schema = EXCLUDED.state_schema,
            schema_etag = EXCLUDED.schema_etag,
            last_fetched_at = EXCLUDED.last_fetched_at,
            updated_at = NOW();

        PERFORM langconnect.increment_cache_version('schemas');
        version_incremented := TRUE;
    END IF;

    RETURN version_incremented;
END;
$$ LANGUAGE plpgsql;

-- Upsert graph schemas with change detection and version increment
CREATE OR REPLACE FUNCTION langconnect.upsert_graph_schemas(
    p_graph_id TEXT,
    p_input_schema JSONB,
    p_config_schema JSONB,
    p_state_schema JSONB
) RETURNS BOOLEAN AS $$
DECLARE
    new_etag TEXT;
    existing_etag TEXT;
    version_incremented BOOLEAN := FALSE;
BEGIN
    BEGIN
        new_etag := encode(
            digest(
                COALESCE(p_input_schema::text, 'null') ||
                COALESCE(p_config_schema::text, 'null') ||
                COALESCE(p_state_schema::text, 'null'),
                'sha256'
            ),
            'hex'
        );
    EXCEPTION WHEN undefined_function THEN
        new_etag := hashtext(
            COALESCE(p_input_schema::text, 'null') ||
            COALESCE(p_config_schema::text, 'null') ||
            COALESCE(p_state_schema::text, 'null')
        )::text;
    END;

    SELECT schema_etag INTO existing_etag
    FROM langconnect.graph_schemas
    WHERE graph_id = p_graph_id;

    IF existing_etag IS NULL OR existing_etag != new_etag THEN
        INSERT INTO langconnect.graph_schemas (
            graph_id, input_schema, config_schema, state_schema,
            schema_etag, last_fetched_at
        ) VALUES (
            p_graph_id, p_input_schema, p_config_schema, p_state_schema,
            new_etag, NOW()
        )
        ON CONFLICT (graph_id) DO UPDATE SET
            input_schema = EXCLUDED.input_schema,
            config_schema = EXCLUDED.config_schema,
            state_schema = EXCLUDED.state_schema,
            schema_etag = EXCLUDED.schema_etag,
            last_fetched_at = EXCLUDED.last_fetched_at,
            updated_at = NOW();

        PERFORM langconnect.increment_cache_version('graph_schemas');
        version_incremented := TRUE;
    END IF;

    RETURN version_incremented;
END;
$$ LANGUAGE plpgsql;

-- Upsert thread metadata into mirror with version increment (fixed from migration 005)
CREATE OR REPLACE FUNCTION langconnect.upsert_thread_mirror(
    p_thread_id UUID,
    p_assistant_id UUID,
    p_graph_id TEXT,
    p_user_id TEXT,
    p_name TEXT,
    p_status TEXT,
    p_last_message_at TIMESTAMPTZ,
    p_langgraph_created_at TIMESTAMPTZ,
    p_langgraph_updated_at TIMESTAMPTZ
) RETURNS BOOLEAN AS $$
DECLARE
    version_incremented BOOLEAN := FALSE;
    existing_thread RECORD;
BEGIN
    SELECT * INTO existing_thread
    FROM langconnect.threads_mirror
    WHERE thread_id = p_thread_id;
    
    INSERT INTO langconnect.threads_mirror (
        thread_id, assistant_id, graph_id, user_id, name, status,
        last_message_at, langgraph_created_at, langgraph_updated_at
    ) VALUES (
        p_thread_id, p_assistant_id, p_graph_id, p_user_id, p_name, p_status,
        p_last_message_at, p_langgraph_created_at, p_langgraph_updated_at
    )
    ON CONFLICT (thread_id) DO UPDATE SET
        assistant_id = COALESCE(EXCLUDED.assistant_id, threads_mirror.assistant_id),
        graph_id = COALESCE(EXCLUDED.graph_id, threads_mirror.graph_id),
        user_id = COALESCE(EXCLUDED.user_id, threads_mirror.user_id),
        name = CASE 
            WHEN EXCLUDED.name IS NOT NULL THEN EXCLUDED.name
            ELSE threads_mirror.name
        END,
        status = COALESCE(EXCLUDED.status, threads_mirror.status),
        last_message_at = COALESCE(EXCLUDED.last_message_at, threads_mirror.last_message_at),
        langgraph_created_at = EXCLUDED.langgraph_created_at,
        langgraph_updated_at = COALESCE(EXCLUDED.langgraph_updated_at, threads_mirror.langgraph_updated_at),
        mirror_updated_at = CASE 
            WHEN threads_mirror.assistant_id IS DISTINCT FROM COALESCE(EXCLUDED.assistant_id, threads_mirror.assistant_id) OR
                 threads_mirror.status IS DISTINCT FROM COALESCE(EXCLUDED.status, threads_mirror.status) OR
                 threads_mirror.last_message_at IS DISTINCT FROM COALESCE(EXCLUDED.last_message_at, threads_mirror.last_message_at) OR
                 threads_mirror.name IS DISTINCT FROM (CASE WHEN EXCLUDED.name IS NOT NULL THEN EXCLUDED.name ELSE threads_mirror.name END)
            THEN NOW()
            ELSE threads_mirror.mirror_updated_at
        END,
        updated_at = CASE 
            WHEN threads_mirror.assistant_id IS DISTINCT FROM COALESCE(EXCLUDED.assistant_id, threads_mirror.assistant_id) OR
                 threads_mirror.status IS DISTINCT FROM COALESCE(EXCLUDED.status, threads_mirror.status) OR
                 threads_mirror.last_message_at IS DISTINCT FROM COALESCE(EXCLUDED.last_message_at, threads_mirror.last_message_at) OR
                 threads_mirror.name IS DISTINCT FROM (CASE WHEN EXCLUDED.name IS NOT NULL THEN EXCLUDED.name ELSE threads_mirror.name END)
            THEN NOW()
            ELSE threads_mirror.updated_at
        END;
    
    IF existing_thread IS NULL OR 
       existing_thread.assistant_id IS DISTINCT FROM p_assistant_id OR
       existing_thread.status IS DISTINCT FROM p_status OR
       existing_thread.last_message_at IS DISTINCT FROM p_last_message_at THEN
        PERFORM langconnect.increment_cache_version('threads');
        version_incremented := TRUE;
    END IF;
    
    RETURN version_incremented;
END;
$$ LANGUAGE plpgsql;

-- Admin retired graphs table (from 003)
CREATE TABLE IF NOT EXISTS langconnect.admin_retired_graphs (
  graph_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'marked' CHECK (status IN ('marked','pruned')),
  reason TEXT,
  notes TEXT,
  marked_by UUID,
  marked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  pruned_by UUID,
  pruned_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_marked_by_user FOREIGN KEY (marked_by) REFERENCES auth.users(id) ON DELETE SET NULL,
  CONSTRAINT fk_pruned_by_user FOREIGN KEY (pruned_by) REFERENCES auth.users(id) ON DELETE SET NULL
);

-- ============================================================================
-- MEM0 MEMORY SYSTEM TABLES
-- ============================================================================

-- Memory table (history store) for storing raw memory content and metadata
-- Memory system tables for mem0 integration
-- mem0 expects specific table structures for compatibility

-- Enable vector extension for embeddings (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Memories table compatible with mem0 PGVector provider
-- This table structure matches what PGVector provider expects
CREATE TABLE IF NOT EXISTS langconnect.memories (
  id UUID PRIMARY KEY,
  vector VECTOR(1536),
  payload JSONB
);

-- HNSW index for efficient vector similarity search
CREATE INDEX IF NOT EXISTS memories_hnsw_idx
ON langconnect.memories
USING hnsw (vector vector_cosine_ops);

-- PGVector migrations table (used by mem0 PGVector provider internally)
CREATE TABLE IF NOT EXISTS langconnect.mem0migrations (
  id UUID PRIMARY KEY,
  vector VECTOR(1536),
  payload JSONB
);

-- HNSW index for mem0migrations table
CREATE INDEX IF NOT EXISTS mem0migrations_hnsw_idx
ON langconnect.mem0migrations
USING hnsw (vector vector_cosine_ops);

-- Vector similarity search function for memories (updated for PGVector schema)
CREATE OR REPLACE FUNCTION langconnect.match_vectors(
  query_embedding VECTOR(1536),
  match_count INT,
  filter JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  id UUID,
  similarity FLOAT,
  payload JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    t.id,
    1 - (t.vector <=> query_embedding) AS similarity,
    t.payload
  FROM langconnect.memories t
  WHERE CASE
    WHEN filter::TEXT = '{}'::TEXT THEN TRUE
    ELSE t.payload @> filter
  END
  ORDER BY t.vector <=> query_embedding
  LIMIT match_count;
END;
$$;


-- Indexes
CREATE INDEX IF NOT EXISTS idx_document_collection_id ON langconnect.langchain_pg_document(collection_id);
CREATE INDEX IF NOT EXISTS idx_embedding_collection_id ON langconnect.langchain_pg_embedding(collection_id);
CREATE INDEX IF NOT EXISTS idx_embedding_document_id ON langconnect.langchain_pg_embedding(document_id);
CREATE INDEX IF NOT EXISTS idx_embedding_document_lookup ON langconnect.langchain_pg_embedding(document_id, collection_id);

CREATE INDEX IF NOT EXISTS idx_collection_permissions_user_id ON langconnect.collection_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_graph_permissions_user_id ON langconnect.graph_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_assistant_permissions_user_id ON langconnect.assistant_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_public_graph_permissions_graph_id ON langconnect.public_graph_permissions(graph_id);
CREATE INDEX IF NOT EXISTS idx_public_assistant_permissions_assistant_id ON langconnect.public_assistant_permissions(assistant_id);
CREATE INDEX IF NOT EXISTS idx_public_collection_permissions_collection_id ON langconnect.public_collection_permissions(collection_id);

CREATE INDEX IF NOT EXISTS idx_graphs_mirror_has_default ON langconnect.graphs_mirror(has_default_assistant);
CREATE INDEX IF NOT EXISTS idx_graphs_mirror_schema_accessible ON langconnect.graphs_mirror(schema_accessible);
CREATE INDEX IF NOT EXISTS idx_graphs_mirror_last_seen ON langconnect.graphs_mirror(langgraph_last_seen_at);
CREATE INDEX IF NOT EXISTS idx_graphs_mirror_updated ON langconnect.graphs_mirror(mirror_updated_at);
CREATE INDEX IF NOT EXISTS idx_assistants_mirror_graph_id ON langconnect.assistants_mirror(graph_id);
CREATE INDEX IF NOT EXISTS idx_assistants_mirror_name ON langconnect.assistants_mirror(name);
CREATE INDEX IF NOT EXISTS idx_assistants_mirror_lg_updated ON langconnect.assistants_mirror(langgraph_updated_at);
CREATE INDEX IF NOT EXISTS idx_assistants_mirror_version ON langconnect.assistants_mirror(version);
CREATE INDEX IF NOT EXISTS idx_assistants_mirror_last_seen ON langconnect.assistants_mirror(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_assistants_mirror_hash ON langconnect.assistants_mirror(langgraph_hash);
CREATE INDEX IF NOT EXISTS idx_assistant_schemas_last_fetched ON langconnect.assistant_schemas(last_fetched_at);
CREATE INDEX IF NOT EXISTS idx_assistant_schemas_etag ON langconnect.assistant_schemas(schema_etag);
CREATE INDEX IF NOT EXISTS idx_graph_schemas_last_fetched ON langconnect.graph_schemas(last_fetched_at);
CREATE INDEX IF NOT EXISTS idx_graph_schemas_etag ON langconnect.graph_schemas(schema_etag);
CREATE INDEX IF NOT EXISTS idx_threads_mirror_user_id ON langconnect.threads_mirror(user_id);
CREATE INDEX IF NOT EXISTS idx_threads_mirror_assistant_id ON langconnect.threads_mirror(assistant_id);
CREATE INDEX IF NOT EXISTS idx_threads_mirror_graph_id ON langconnect.threads_mirror(graph_id);
CREATE INDEX IF NOT EXISTS idx_threads_mirror_last_message ON langconnect.threads_mirror(last_message_at);
CREATE INDEX IF NOT EXISTS idx_threads_mirror_status ON langconnect.threads_mirror(status);
CREATE INDEX IF NOT EXISTS idx_threads_mirror_lg_created ON langconnect.threads_mirror(langgraph_created_at);
CREATE INDEX IF NOT EXISTS idx_admin_retired_graphs_status ON langconnect.admin_retired_graphs(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_user_id ON langconnect.processing_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_collection_id ON langconnect.processing_jobs(collection_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON langconnect.processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_created_at ON langconnect.processing_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_user_status_created ON langconnect.processing_jobs(user_id, status, created_at DESC);

-- Functions for roles and public permission auto-grant
CREATE OR REPLACE FUNCTION langconnect.extract_display_name(user_metadata JSONB, fallback_email VARCHAR)
RETURNS VARCHAR AS $$
BEGIN
  IF user_metadata ? 'name' AND user_metadata->>'name' IS NOT NULL AND trim(user_metadata->>'name') != '' THEN
    RETURN trim(user_metadata->>'name');
  END IF;
  IF user_metadata ? 'first_name' AND user_metadata ? 'last_name'
     AND user_metadata->>'first_name' IS NOT NULL AND user_metadata->>'last_name' IS NOT NULL
     AND trim(user_metadata->>'first_name') != '' AND trim(user_metadata->>'last_name') != '' THEN
    RETURN trim(user_metadata->>'first_name') || ' ' || trim(user_metadata->>'last_name');
  END IF;
  IF user_metadata ? 'first_name' AND user_metadata->>'first_name' IS NOT NULL AND trim(user_metadata->>'first_name') != '' THEN
    RETURN trim(user_metadata->>'first_name');
  END IF;
  RETURN fallback_email;
END; $$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION langconnect.auto_create_user_role()
RETURNS TRIGGER AS $$
DECLARE 
  user_display_name VARCHAR;
  user_count INTEGER;
  assigned_role VARCHAR;
BEGIN
  user_display_name := langconnect.extract_display_name(COALESCE(NEW.raw_user_meta_data, '{}'::jsonb), NEW.email);
  
  -- Check if this is the first user by counting existing user_roles (from 011)
  SELECT COUNT(*) INTO user_count FROM langconnect.user_roles;
  
  -- Assign dev_admin role to the first user, regular user role to others
  IF user_count = 0 THEN
    assigned_role := 'dev_admin';
  ELSE
    assigned_role := 'user';
  END IF;
  
  INSERT INTO langconnect.user_roles (user_id, role, email, display_name, assigned_by)
  VALUES (NEW.id::text, assigned_role, NEW.email, user_display_name, 
    CASE WHEN assigned_role = 'dev_admin' THEN 'system:first_user' ELSE 'system' END)
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END; $$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION langconnect.auto_grant_public_permissions()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO langconnect.graph_permissions (user_id, graph_id, permission_level, granted_by)
  SELECT NEW.id::VARCHAR, graph_id, permission_level, 'system:public'
  FROM langconnect.public_graph_permissions WHERE revoked_at IS NULL
  ON CONFLICT (user_id, graph_id) DO NOTHING;

  INSERT INTO langconnect.assistant_permissions (user_id, assistant_id, permission_level, granted_by)
  SELECT NEW.id::VARCHAR, assistant_id::UUID, permission_level, 'system:public'
  FROM langconnect.public_assistant_permissions WHERE revoked_at IS NULL
  ON CONFLICT (user_id, assistant_id) DO NOTHING;

  INSERT INTO langconnect.collection_permissions (user_id, collection_id, permission_level, granted_by)
  SELECT NEW.id::VARCHAR, collection_id, permission_level, 'system:public'
  FROM langconnect.public_collection_permissions WHERE revoked_at IS NULL
  ON CONFLICT (collection_id, user_id) DO NOTHING;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

-- Function to accept notification and grant permission (from archive migration 009)
CREATE OR REPLACE FUNCTION langconnect.accept_notification(p_notification_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    notification_record RECORD;
    success BOOLEAN := FALSE;
BEGIN
    -- Get notification details
    SELECT * INTO notification_record
    FROM langconnect.notifications
    WHERE id = p_notification_id AND status = 'pending';
    
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    
    -- Grant permission based on resource type
    IF notification_record.resource_type = 'graph' THEN
        INSERT INTO langconnect.graph_permissions (graph_id, user_id, permission_level, granted_by)
        VALUES (notification_record.resource_id, notification_record.recipient_user_id::VARCHAR, 
                notification_record.permission_level, notification_record.sender_user_id::VARCHAR)
        ON CONFLICT (graph_id, user_id) DO UPDATE SET
            permission_level = EXCLUDED.permission_level,
            granted_by = EXCLUDED.granted_by,
            updated_at = NOW();
        success := TRUE;
    ELSIF notification_record.resource_type = 'assistant' THEN
        INSERT INTO langconnect.assistant_permissions (assistant_id, user_id, permission_level, granted_by)
        VALUES (notification_record.resource_id::UUID, notification_record.recipient_user_id::VARCHAR,
                notification_record.permission_level, notification_record.sender_user_id::VARCHAR)
        ON CONFLICT (assistant_id, user_id) DO UPDATE SET
            permission_level = EXCLUDED.permission_level,
            granted_by = EXCLUDED.granted_by,
            updated_at = NOW();
        success := TRUE;
    ELSIF notification_record.resource_type = 'collection' THEN
        INSERT INTO langconnect.collection_permissions (collection_id, user_id, permission_level, granted_by)
        VALUES (notification_record.resource_id::UUID, notification_record.recipient_user_id::VARCHAR,
                notification_record.permission_level, notification_record.sender_user_id::VARCHAR)
        ON CONFLICT (collection_id, user_id) DO UPDATE SET
            permission_level = EXCLUDED.permission_level,
            granted_by = EXCLUDED.granted_by,
            updated_at = NOW();
        success := TRUE;
    END IF;
    
    -- Update notification status
    IF success THEN
        UPDATE langconnect.notifications
        SET status = 'accepted', responded_at = NOW()
        WHERE id = p_notification_id;
    END IF;
    
    RETURN success;
END;
$$ LANGUAGE plpgsql;

-- Create a new notification (from archive)
CREATE OR REPLACE FUNCTION langconnect.create_notification(
    p_recipient_user_id UUID,
    p_type langconnect.notification_type,
    p_resource_id VARCHAR,
    p_resource_type VARCHAR,
    p_permission_level VARCHAR,
    p_sender_user_id UUID,
    p_sender_display_name VARCHAR,
    p_resource_name VARCHAR,
    p_resource_description TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    new_notification_id UUID;
BEGIN
    INSERT INTO langconnect.notifications (
        recipient_user_id, type, resource_id, resource_type, permission_level,
        sender_user_id, sender_display_name, resource_name, resource_description
    ) VALUES (
        p_recipient_user_id, p_type, p_resource_id, p_resource_type, p_permission_level,
        p_sender_user_id, p_sender_display_name, p_resource_name, p_resource_description
    ) RETURNING id INTO new_notification_id;
    
    RETURN new_notification_id;
END;
$$ LANGUAGE plpgsql;

-- Reject notification (from archive)
CREATE OR REPLACE FUNCTION langconnect.reject_notification(p_notification_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE langconnect.notifications
    SET status = 'rejected', responded_at = NOW()
    WHERE id = p_notification_id AND status = 'pending';
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Mark expired notifications as expired (from archive)
CREATE OR REPLACE FUNCTION langconnect.cleanup_expired_notifications()
RETURNS INTEGER AS $$
DECLARE
    expired_count INTEGER;
BEGIN
    UPDATE langconnect.notifications
    SET status = 'expired'
    WHERE status = 'pending' AND expires_at < NOW();
    
    GET DIAGNOSTICS expired_count = ROW_COUNT;
    RETURN expired_count;
END;
$$ LANGUAGE plpgsql;

-- Backfill function for missing user roles (from archive migration 011)
CREATE OR REPLACE FUNCTION langconnect.backfill_missing_user_roles_v2()
RETURNS INTEGER AS $$
DECLARE
    inserted_count INTEGER := 0;
    user_record RECORD;
    is_first_user BOOLEAN := TRUE;
    assigned_role VARCHAR;
BEGIN
    -- Check if we have any existing user roles
    SELECT COUNT(*) > 0 INTO is_first_user
    FROM langconnect.user_roles;
    
    -- If we already have user roles, don't treat anyone as first user
    is_first_user := NOT is_first_user;
    
    -- Insert missing user roles for users who signed up before the trigger was created
    FOR user_record IN 
        SELECT u.id, u.email, u.raw_user_meta_data, u.created_at
        FROM auth.users u
        LEFT JOIN langconnect.user_roles ur ON u.id::VARCHAR = ur.user_id
        WHERE ur.user_id IS NULL
        ORDER BY u.created_at ASC  -- Process in chronological order
    LOOP
        -- First user gets dev_admin, others get user role
        IF is_first_user AND inserted_count = 0 THEN
            assigned_role := 'dev_admin';
        ELSE
            assigned_role := 'user';
        END IF;
        
        INSERT INTO langconnect.user_roles (
            user_id, 
            role, 
            email, 
            display_name, 
            assigned_by
        ) VALUES (
            user_record.id::VARCHAR,
            assigned_role,
            user_record.email,
            langconnect.extract_display_name(user_record.raw_user_meta_data, user_record.email),
            CASE 
                WHEN assigned_role = 'dev_admin' THEN 'system:backfill_first_user'
                ELSE 'system:backfill'
            END
        );
        
        inserted_count := inserted_count + 1;
    END LOOP;
    
    RETURN inserted_count;
END;
$$ LANGUAGE plpgsql;

-- One-time backfill function to grant existing public permissions to all existing users
CREATE OR REPLACE FUNCTION langconnect.backfill_public_permissions()
RETURNS TABLE(graphs_granted INTEGER, assistants_granted INTEGER, collections_granted INTEGER) AS $$
DECLARE
    graph_count INTEGER := 0;
    assistant_count INTEGER := 0;
    collection_count INTEGER := 0;
BEGIN
    -- Grant all active public graph permissions to all existing users
    INSERT INTO langconnect.graph_permissions (user_id, graph_id, permission_level, granted_by)
    SELECT ur.user_id, pgp.graph_id, pgp.permission_level, 'system:public'
    FROM langconnect.user_roles ur
    CROSS JOIN langconnect.public_graph_permissions pgp
    WHERE pgp.revoked_at IS NULL
    ON CONFLICT (user_id, graph_id) DO NOTHING;
    
    GET DIAGNOSTICS graph_count = ROW_COUNT;

    -- Grant all active public assistant permissions to all existing users
    INSERT INTO langconnect.assistant_permissions (user_id, assistant_id, permission_level, granted_by)
    SELECT ur.user_id, pap.assistant_id::UUID, pap.permission_level, 'system:public'
    FROM langconnect.user_roles ur
    CROSS JOIN langconnect.public_assistant_permissions pap
    WHERE pap.revoked_at IS NULL
    ON CONFLICT (user_id, assistant_id) DO NOTHING;
    
    GET DIAGNOSTICS assistant_count = ROW_COUNT;

    -- Grant all active public collection permissions to all existing users
    INSERT INTO langconnect.collection_permissions (user_id, collection_id, permission_level, granted_by)
    SELECT ur.user_id, pcp.collection_id, pcp.permission_level, 'system:public'
    FROM langconnect.user_roles ur
    CROSS JOIN langconnect.public_collection_permissions pcp
    WHERE pcp.revoked_at IS NULL
    ON CONFLICT (collection_id, user_id) DO NOTHING;
    
    GET DIAGNOSTICS collection_count = ROW_COUNT;

    RETURN QUERY SELECT graph_count, assistant_count, collection_count;
END;
$$ LANGUAGE plpgsql;

-- Job progress update function (from archived migration 008)
CREATE OR REPLACE FUNCTION langconnect.update_job_progress(
    job_id UUID,
    new_status langconnect.job_status DEFAULT NULL,
    new_progress INTEGER DEFAULT NULL,
    new_step VARCHAR DEFAULT NULL,
    new_error TEXT DEFAULT NULL,
    new_error_details JSONB DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    job_exists BOOLEAN;
BEGIN
    SELECT EXISTS(SELECT 1 FROM langconnect.processing_jobs WHERE id = job_id) INTO job_exists;
    
    IF NOT job_exists THEN
        RAISE EXCEPTION 'Job with ID % not found', job_id;
    END IF;
    
    UPDATE langconnect.processing_jobs 
    SET 
        status = COALESCE(new_status, status),
        progress_percent = COALESCE(new_progress, progress_percent),
        current_step = COALESCE(new_step, current_step),
        error_message = COALESCE(new_error, error_message),
        error_details = COALESCE(new_error_details, error_details),
        started_at = CASE 
            WHEN new_status = 'processing' AND started_at IS NULL THEN NOW()
            ELSE started_at 
        END,
        completed_at = CASE 
            WHEN new_status IN ('completed', 'failed', 'cancelled') AND completed_at IS NULL THEN NOW()
            ELSE completed_at 
        END,
        processing_time_seconds = CASE 
            WHEN new_status IN ('completed', 'failed', 'cancelled') AND started_at IS NOT NULL THEN 
                EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER
            ELSE processing_time_seconds 
        END
    WHERE id = job_id;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Cleanup function for old jobs (from archived migration 008)
CREATE OR REPLACE FUNCTION langconnect.cleanup_old_jobs() RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM langconnect.processing_jobs
    WHERE status IN ('completed', 'failed', 'cancelled')
    AND completed_at < NOW() - INTERVAL '30 days';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to auto-reassign default assistant when current default is deleted
CREATE OR REPLACE FUNCTION langconnect.reassign_default_assistant_on_delete()
RETURNS TRIGGER AS $$
DECLARE
    affected_user VARCHAR;
    new_default_assistant UUID;
BEGIN
    -- Find users who had this assistant as default
    FOR affected_user IN
        SELECT user_id FROM langconnect.user_default_assistants
        WHERE assistant_id = OLD.assistant_id
    LOOP
        -- Find another assistant the user has access to (prioritize owned, then most recent)
        SELECT ap.assistant_id INTO new_default_assistant
        FROM langconnect.assistant_permissions ap
        JOIN langconnect.assistants_mirror am ON ap.assistant_id = am.assistant_id
        WHERE ap.user_id = affected_user
          AND ap.assistant_id != OLD.assistant_id
        ORDER BY
            CASE WHEN ap.permission_level = 'owner' THEN 1
                 WHEN ap.permission_level = 'editor' THEN 2
                 ELSE 3 END,
            am.created_at DESC
        LIMIT 1;

        -- If found another assistant, update default; otherwise delete the default entry
        IF new_default_assistant IS NOT NULL THEN
            UPDATE langconnect.user_default_assistants
            SET assistant_id = new_default_assistant, updated_at = NOW()
            WHERE user_id = affected_user;

            RAISE NOTICE 'Auto-reassigned default assistant for user % to %',
                affected_user, new_default_assistant;
        ELSE
            DELETE FROM langconnect.user_default_assistants
            WHERE user_id = affected_user;

            RAISE NOTICE 'Removed default assistant for user % (no other assistants available)',
                affected_user;
        END IF;
    END LOOP;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Function to clear default when user loses access to their default assistant
CREATE OR REPLACE FUNCTION langconnect.check_default_on_permission_revoke()
RETURNS TRIGGER AS $$
DECLARE
    new_default_assistant UUID;
BEGIN
    -- Check if user had this as their default
    IF EXISTS (
        SELECT 1 FROM langconnect.user_default_assistants
        WHERE user_id = OLD.user_id AND assistant_id = OLD.assistant_id
    ) THEN
        -- Find another assistant the user has access to
        SELECT ap.assistant_id INTO new_default_assistant
        FROM langconnect.assistant_permissions ap
        JOIN langconnect.assistants_mirror am ON ap.assistant_id = am.assistant_id
        WHERE ap.user_id = OLD.user_id
          AND ap.assistant_id != OLD.assistant_id
        ORDER BY
            CASE WHEN ap.permission_level = 'owner' THEN 1
                 WHEN ap.permission_level = 'editor' THEN 2
                 ELSE 3 END,
            am.created_at DESC
        LIMIT 1;

        IF new_default_assistant IS NOT NULL THEN
            UPDATE langconnect.user_default_assistants
            SET assistant_id = new_default_assistant, updated_at = NOW()
            WHERE user_id = OLD.user_id;
        ELSE
            DELETE FROM langconnect.user_default_assistants
            WHERE user_id = OLD.user_id;
        END IF;
    END IF;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Sync user role info function (from archived migration)
CREATE OR REPLACE FUNCTION langconnect.sync_user_role_info(target_user_id VARCHAR)
RETURNS VOID AS $$
DECLARE
    user_info RECORD;
BEGIN
    SELECT au.email, au.raw_user_meta_data
    INTO user_info
    FROM auth.users au
    WHERE au.id::text = target_user_id;
    
    IF FOUND THEN
        UPDATE langconnect.user_roles
        SET 
            email = user_info.email,
            display_name = langconnect.extract_display_name(user_info.raw_user_meta_data, user_info.email),
            updated_at = NOW()
        WHERE user_id = target_user_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Notifications table (enums already created above)

CREATE TABLE IF NOT EXISTS langconnect.notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_user_id UUID NOT NULL,
  type langconnect.notification_type NOT NULL,
  resource_id VARCHAR NOT NULL,
  resource_type VARCHAR NOT NULL CHECK (resource_type IN ('graph','assistant','collection')),
  permission_level VARCHAR NOT NULL,
  sender_user_id UUID NOT NULL,
  sender_display_name VARCHAR,
  status langconnect.notification_status NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  responded_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days'),
  resource_name VARCHAR NOT NULL,
  resource_description TEXT,
  CONSTRAINT fk_recipient FOREIGN KEY (recipient_user_id) REFERENCES auth.users(id) ON DELETE CASCADE,
  CONSTRAINT fk_sender FOREIGN KEY (sender_user_id) REFERENCES auth.users(id) ON DELETE CASCADE
);

-- Add foreign key constraints (from 006 and 007)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE table_schema = 'langconnect' AND table_name = 'assistant_permissions' AND constraint_name = 'fk_assistant_permissions_assistant'
  ) THEN
    ALTER TABLE langconnect.assistant_permissions
    ADD CONSTRAINT fk_assistant_permissions_assistant
    FOREIGN KEY (assistant_id) REFERENCES langconnect.assistants_mirror(assistant_id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE table_schema = 'langconnect' AND table_name = 'graph_permissions' AND constraint_name = 'fk_graph_permissions_graph'
  ) THEN
    ALTER TABLE langconnect.graph_permissions
    ADD CONSTRAINT fk_graph_permissions_graph
    FOREIGN KEY (graph_id) REFERENCES langconnect.graphs_mirror(graph_id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE table_schema = 'langconnect' AND table_name = 'graph_permissions' AND constraint_name = 'fk_graph_permissions_user'
  ) THEN
    ALTER TABLE langconnect.graph_permissions
    ADD CONSTRAINT fk_graph_permissions_user
    FOREIGN KEY (user_id) REFERENCES langconnect.user_roles(user_id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE table_schema = 'langconnect' AND table_name = 'assistant_permissions' AND constraint_name = 'fk_assistant_permissions_user'
  ) THEN
    ALTER TABLE langconnect.assistant_permissions
    ADD CONSTRAINT fk_assistant_permissions_user
    FOREIGN KEY (user_id) REFERENCES langconnect.user_roles(user_id) ON DELETE CASCADE;
  END IF;
END $$;

-- Triggers
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_user_roles_updated_at') THEN
    CREATE TRIGGER trigger_user_roles_updated_at BEFORE UPDATE ON langconnect.user_roles FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_graph_permissions_updated_at') THEN
    CREATE TRIGGER trigger_graph_permissions_updated_at BEFORE UPDATE ON langconnect.graph_permissions FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_assistant_permissions_updated_at') THEN
    CREATE TRIGGER trigger_assistant_permissions_updated_at BEFORE UPDATE ON langconnect.assistant_permissions FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_collection_permissions_updated_at') THEN
    CREATE TRIGGER trigger_collection_permissions_updated_at BEFORE UPDATE ON langconnect.collection_permissions FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_user_default_assistants_updated_at') THEN
    CREATE TRIGGER trigger_user_default_assistants_updated_at BEFORE UPDATE ON langconnect.user_default_assistants FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_reassign_default_on_assistant_delete') THEN
    CREATE TRIGGER trigger_reassign_default_on_assistant_delete BEFORE DELETE ON langconnect.assistants_mirror FOR EACH ROW EXECUTE FUNCTION langconnect.reassign_default_assistant_on_delete();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_check_default_on_permission_revoke') THEN
    CREATE TRIGGER trigger_check_default_on_permission_revoke BEFORE DELETE ON langconnect.assistant_permissions FOR EACH ROW EXECUTE FUNCTION langconnect.check_default_on_permission_revoke();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_admin_retired_graphs_updated_at') THEN
    CREATE TRIGGER trigger_admin_retired_graphs_updated_at BEFORE UPDATE ON langconnect.admin_retired_graphs FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_graphs_mirror_updated_at') THEN
    CREATE TRIGGER trigger_graphs_mirror_updated_at BEFORE UPDATE ON langconnect.graphs_mirror FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_assistants_mirror_updated_at') THEN
    CREATE TRIGGER trigger_assistants_mirror_updated_at BEFORE UPDATE ON langconnect.assistants_mirror FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_assistant_schemas_updated_at') THEN
    CREATE TRIGGER trigger_assistant_schemas_updated_at BEFORE UPDATE ON langconnect.assistant_schemas FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_graph_schemas_updated_at') THEN
    CREATE TRIGGER trigger_graph_schemas_updated_at BEFORE UPDATE ON langconnect.graph_schemas FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_threads_mirror_updated_at') THEN
    CREATE TRIGGER trigger_threads_mirror_updated_at BEFORE UPDATE ON langconnect.threads_mirror FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_cache_state_updated_at') THEN
    CREATE TRIGGER trigger_cache_state_updated_at BEFORE UPDATE ON langconnect.cache_state FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_langchain_pg_collection_updated_at') THEN
    CREATE TRIGGER trigger_langchain_pg_collection_updated_at BEFORE UPDATE ON langconnect.langchain_pg_collection FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_langchain_pg_document_updated_at') THEN
    CREATE TRIGGER trigger_langchain_pg_document_updated_at BEFORE UPDATE ON langconnect.langchain_pg_document FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_langchain_pg_embedding_updated_at') THEN
    CREATE TRIGGER trigger_langchain_pg_embedding_updated_at BEFORE UPDATE ON langconnect.langchain_pg_embedding FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_notifications_updated_at') THEN
    CREATE TRIGGER trigger_notifications_updated_at BEFORE UPDATE ON langconnect.notifications FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_public_graph_permissions_updated_at') THEN
    CREATE TRIGGER trigger_public_graph_permissions_updated_at BEFORE UPDATE ON langconnect.public_graph_permissions FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_public_assistant_permissions_updated_at') THEN
    CREATE TRIGGER trigger_public_assistant_permissions_updated_at BEFORE UPDATE ON langconnect.public_assistant_permissions FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_public_collection_permissions_updated_at') THEN
    CREATE TRIGGER trigger_public_collection_permissions_updated_at BEFORE UPDATE ON langconnect.public_collection_permissions FOR EACH ROW EXECUTE FUNCTION langconnect.update_updated_at_column();
  END IF;
END $$;

-- Memory system triggers
-- Note: No triggers needed for memories table as it uses simple PGVector structure without timestamps

DO $$ BEGIN
  BEGIN
    GRANT USAGE ON SCHEMA langconnect TO supabase_auth_admin;
    GRANT EXECUTE ON FUNCTION langconnect.auto_create_user_role() TO supabase_auth_admin;
    GRANT EXECUTE ON FUNCTION langconnect.auto_grant_public_permissions() TO supabase_auth_admin;
    GRANT INSERT, SELECT ON langconnect.user_roles TO supabase_auth_admin;
    GRANT INSERT, SELECT ON langconnect.graph_permissions TO supabase_auth_admin;
    GRANT INSERT, SELECT ON langconnect.assistant_permissions TO supabase_auth_admin;
    GRANT INSERT, SELECT ON langconnect.collection_permissions TO supabase_auth_admin;
    GRANT SELECT ON langconnect.public_graph_permissions TO supabase_auth_admin;
    GRANT SELECT ON langconnect.public_assistant_permissions TO supabase_auth_admin;
    GRANT INSERT, SELECT, UPDATE ON langconnect.public_collection_permissions TO supabase_auth_admin;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_auto_create_user_role') THEN
    CREATE TRIGGER trigger_auto_create_user_role AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION langconnect.auto_create_user_role();
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_auto_grant_public_permissions') THEN
    CREATE TRIGGER trigger_auto_grant_public_permissions AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION langconnect.auto_grant_public_permissions();
  END IF;
END $$;

-- Optional realtime publication (guarded)
DO $$ BEGIN
  BEGIN
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables WHERE pubname = 'supabase_realtime' AND schemaname = 'langconnect' AND tablename = 'processing_jobs'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE langconnect.processing_jobs;
    END IF;
    GRANT SELECT ON langconnect.processing_jobs TO authenticated;
  EXCEPTION WHEN undefined_object THEN NULL; END;
END $$;

-- ============================================================================
-- COMMENTS AND DOCUMENTATION (from archived migrations)
-- ============================================================================

-- Core LangChain tables
COMMENT ON TABLE langconnect.langchain_pg_collection IS 'LangChain collections for organizing documents and embeddings';
COMMENT ON TABLE langconnect.langchain_pg_document IS 'Full document storage - contains complete document content and metadata';
COMMENT ON TABLE langconnect.langchain_pg_embedding IS 'Text chunks with vector embeddings for RAG search';

COMMENT ON COLUMN langconnect.langchain_pg_document.content IS 'Complete document content (full text) - LangChain compatible column name';
COMMENT ON COLUMN langconnect.langchain_pg_embedding.document IS 'Text content of this chunk - LangChain PGVector compatible column name';
COMMENT ON COLUMN langconnect.langchain_pg_embedding.document_id IS 'Foreign key reference to parent document';
COMMENT ON COLUMN langconnect.langchain_pg_embedding.created_at IS 'Timestamp when this chunk was created';
COMMENT ON COLUMN langconnect.langchain_pg_embedding.updated_at IS 'Timestamp when this chunk was last updated (auto-updated by trigger)';

-- Permission system tables
COMMENT ON TABLE langconnect.collection_permissions IS 'Permissions for collection sharing and collaboration';
COMMENT ON TABLE langconnect.user_roles IS 'User role assignments for agent collaboration system';
COMMENT ON COLUMN langconnect.user_roles.user_id IS 'References Supabase auth.users(id)';
COMMENT ON COLUMN langconnect.user_roles.role IS 'User role: dev_admin, business_admin, or user';
COMMENT ON COLUMN langconnect.user_roles.assigned_by IS 'User ID who assigned this role';
COMMENT ON COLUMN langconnect.user_roles.email IS 'User email address from auth.users table';
COMMENT ON COLUMN langconnect.user_roles.display_name IS 'User display name extracted from auth.users metadata';

COMMENT ON TABLE langconnect.graph_permissions IS 'Graph-level permissions controlling access to base graphs';
COMMENT ON COLUMN langconnect.graph_permissions.graph_id IS 'Graph identifier from langgraph.json configuration';
COMMENT ON COLUMN langconnect.graph_permissions.user_id IS 'References Supabase auth.users(id)';
COMMENT ON COLUMN langconnect.graph_permissions.permission_level IS 'Permission level: admin (can manage permissions) or access (can create assistants)';
COMMENT ON COLUMN langconnect.graph_permissions.granted_by IS 'User ID who granted this permission';

COMMENT ON TABLE langconnect.assistant_permissions IS 'Assistant-level permissions controlling who can use specific assistants';
COMMENT ON COLUMN langconnect.assistant_permissions.assistant_id IS 'LangGraph assistant identifier';
COMMENT ON COLUMN langconnect.assistant_permissions.user_id IS 'References Supabase auth.users(id)';
COMMENT ON COLUMN langconnect.assistant_permissions.permission_level IS 'Permission level: owner (full control), editor (can edit), viewer (read-only)';
COMMENT ON COLUMN langconnect.assistant_permissions.granted_by IS 'User ID who granted this permission';

COMMENT ON TABLE langconnect.user_default_assistants IS 'User default assistant selection for auto-selection in chat interface. Auto-reassigns to another assistant if default is deleted or access is revoked.';
COMMENT ON COLUMN langconnect.user_default_assistants.user_id IS 'References langconnect.user_roles(user_id)';
COMMENT ON COLUMN langconnect.user_default_assistants.assistant_id IS 'The assistant ID set as default for this user. First created assistant is auto-set as default.';

COMMENT ON TABLE langconnect.public_graph_permissions IS 'Defines which graphs have public (default) access for all users';
COMMENT ON COLUMN langconnect.public_graph_permissions.graph_id IS 'The graph ID that should have public access';
COMMENT ON COLUMN langconnect.public_graph_permissions.permission_level IS 'Permission level granted to all users (access or admin)';
COMMENT ON COLUMN langconnect.public_graph_permissions.revoke_mode IS 'How to handle revocation: revoke_all removes all user permissions, future_only only affects new users';

COMMENT ON TABLE langconnect.public_assistant_permissions IS 'Defines which assistants have public (default) access for all users';
COMMENT ON COLUMN langconnect.public_assistant_permissions.assistant_id IS 'The assistant ID that should have public access';
COMMENT ON COLUMN langconnect.public_assistant_permissions.permission_level IS 'Permission level granted to all users (viewer, editor, or owner)';
COMMENT ON COLUMN langconnect.public_assistant_permissions.revoke_mode IS 'How to handle revocation: revoke_all removes all user permissions, future_only only affects new users';

COMMENT ON TABLE langconnect.notifications IS 'Notification system for permission sharing requests';
COMMENT ON COLUMN langconnect.notifications.recipient_user_id IS 'UUID of user who receives the notification (references auth.users.id)';
COMMENT ON COLUMN langconnect.notifications.type IS 'Type of notification: graph_share, assistant_share, or collection_share';
COMMENT ON COLUMN langconnect.notifications.resource_id IS 'ID of the resource being shared';
COMMENT ON COLUMN langconnect.notifications.resource_type IS 'Type of resource: graph, assistant, or collection';
COMMENT ON COLUMN langconnect.notifications.permission_level IS 'Permission level being offered';
COMMENT ON COLUMN langconnect.notifications.sender_user_id IS 'UUID of user who initiated the sharing (references auth.users.id)';
COMMENT ON COLUMN langconnect.notifications.status IS 'Current status: pending, accepted, rejected, or expired';
COMMENT ON COLUMN langconnect.notifications.resource_name IS 'Snapshot of resource name for display purposes';
COMMENT ON COLUMN langconnect.notifications.expires_at IS 'When this notification expires (defaults to 30 days)';

-- Mirror tables comments
COMMENT ON TABLE langconnect.graphs_mirror IS 'Faithful mirror of LangGraph graphs (derived from assistants by graph_id)';
COMMENT ON COLUMN langconnect.graphs_mirror.graph_id IS 'Graph identifier from LangGraph deployment';
COMMENT ON COLUMN langconnect.graphs_mirror.assistants_count IS 'Number of assistants in this graph (computed from assistants_mirror)';
COMMENT ON COLUMN langconnect.graphs_mirror.has_default_assistant IS 'Whether this graph has a system default assistant (graph template enhanced with user-friendly metadata)';
COMMENT ON COLUMN langconnect.graphs_mirror.name IS 'Human-readable graph name (editable by admins; defaults to title-cased graph_id)';
COMMENT ON COLUMN langconnect.graphs_mirror.description IS 'Optional human-authored description for this graph (editable by admins)';
COMMENT ON COLUMN langconnect.graphs_mirror.schema_accessible IS 'Whether the graph schema endpoint is accessible';
COMMENT ON COLUMN langconnect.graphs_mirror.langgraph_hash IS 'Hash of aggregated assistant data for change detection';

COMMENT ON TABLE langconnect.assistants_mirror IS 'Faithful mirror of LangGraph assistants for fast, consistent reads';
COMMENT ON COLUMN langconnect.assistants_mirror.assistant_id IS 'LangGraph assistant UUID identifier';
COMMENT ON COLUMN langconnect.assistants_mirror.graph_id IS 'Graph this assistant was created from';
COMMENT ON COLUMN langconnect.assistants_mirror.tags IS 'Categorization tags for marketplace filtering (e.g., ["sales", "research", "productivity"])';
COMMENT ON COLUMN langconnect.assistants_mirror.config IS 'Full LangGraph assistant configuration (exact copy)';
COMMENT ON COLUMN langconnect.assistants_mirror.metadata IS 'Full LangGraph assistant metadata (exact copy)';
COMMENT ON COLUMN langconnect.assistants_mirror.context IS 'Full LangGraph assistant context (exact copy)';
COMMENT ON COLUMN langconnect.assistants_mirror.version IS 'LangGraph assistant version number';
COMMENT ON COLUMN langconnect.assistants_mirror.langgraph_hash IS 'Hash of significant fields for change detection';
COMMENT ON COLUMN langconnect.assistants_mirror.description IS 'Top-level LangGraph assistant description (mirrored)';

COMMENT ON TABLE langconnect.assistant_schemas IS 'Cached schemas from LangGraph for fast UI decisions and configuration';
COMMENT ON COLUMN langconnect.assistant_schemas.input_schema IS 'LangGraph input schema (for form/chat mode detection)';
COMMENT ON COLUMN langconnect.assistant_schemas.config_schema IS 'LangGraph config schema (for configuration UI)';
COMMENT ON COLUMN langconnect.assistant_schemas.state_schema IS 'LangGraph state schema (for advanced configuration)';
COMMENT ON COLUMN langconnect.assistant_schemas.schema_etag IS 'Hash of all schemas for change detection';

COMMENT ON TABLE langconnect.graph_schemas IS 'Cached graph template schemas from LangGraph graph template assistants for agent creation UI';
COMMENT ON COLUMN langconnect.graph_schemas.input_schema IS 'LangGraph graph input schema (for form/chat mode detection)';
COMMENT ON COLUMN langconnect.graph_schemas.config_schema IS 'LangGraph graph config schema (for agent creation configuration UI)';
COMMENT ON COLUMN langconnect.graph_schemas.state_schema IS 'LangGraph graph state schema (for advanced configuration)';
COMMENT ON COLUMN langconnect.graph_schemas.schema_etag IS 'Hash of all schemas for change detection';

COMMENT ON TABLE langconnect.threads_mirror IS 'Minimal mirror of LangGraph threads for observability and future UX (no messages stored)';
COMMENT ON COLUMN langconnect.threads_mirror.thread_id IS 'LangGraph thread UUID identifier';
COMMENT ON COLUMN langconnect.threads_mirror.assistant_id IS 'Assistant used in this thread (can be null for orphaned threads)';
COMMENT ON COLUMN langconnect.threads_mirror.user_id IS 'User who created/owns this thread';
COMMENT ON COLUMN langconnect.threads_mirror.name IS 'User-friendly thread name (future: AI-generated from conversation)';
COMMENT ON COLUMN langconnect.threads_mirror.summary IS 'Brief thread summary (future: AI-generated)';
COMMENT ON COLUMN langconnect.threads_mirror.status IS 'Thread status (active, completed, etc.)';

COMMENT ON TABLE langconnect.cache_state IS 'Version tracking for cache invalidation in frontend';
COMMENT ON COLUMN langconnect.cache_state.graphs_version IS 'Incremented when graphs_mirror changes';
COMMENT ON COLUMN langconnect.cache_state.assistants_version IS 'Incremented when assistants_mirror changes';
COMMENT ON COLUMN langconnect.cache_state.schemas_version IS 'Incremented when assistant_schemas changes';
COMMENT ON COLUMN langconnect.cache_state.graph_schemas_version IS 'Incremented when graph_schemas changes';
COMMENT ON COLUMN langconnect.cache_state.threads_version IS 'Incremented when threads_mirror changes';

COMMENT ON TABLE langconnect.admin_retired_graphs IS 'Admin-managed list of retired graphs (hidden from users). Manual prune only.';
COMMENT ON COLUMN langconnect.admin_retired_graphs.status IS 'marked = hidden/unavailable; pruned = manually cleaned up';

COMMENT ON TABLE langconnect.processing_jobs IS 'Background job tracking for document processing and other async operations';


-- Comments for memories table
COMMENT ON TABLE langconnect.memories IS 'Memories table compatible with mem0 PGVector provider for vector storage and retrieval';
COMMENT ON COLUMN langconnect.memories.id IS 'Primary key - UUID identifier for the memory';
COMMENT ON COLUMN langconnect.memories.vector IS 'Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)';
COMMENT ON COLUMN langconnect.memories.payload IS 'JSONB payload including user context, agent context, and memory content';

COMMENT ON TABLE langconnect.mem0migrations IS 'Internal table used by mem0 PGVector provider for schema migrations and metadata';
COMMENT ON COLUMN langconnect.mem0migrations.id IS 'Primary key - UUID identifier';
COMMENT ON COLUMN langconnect.mem0migrations.vector IS 'Vector embedding (1536 dimensions)';
COMMENT ON COLUMN langconnect.mem0migrations.payload IS 'JSONB payload for internal mem0 metadata';

-- Function comments
COMMENT ON FUNCTION langconnect.extract_display_name(JSONB, VARCHAR) IS 'Extract user display name from auth metadata with fallback to email';
COMMENT ON FUNCTION langconnect.sync_user_role_info(VARCHAR) IS 'Sync email and display_name for a specific user_id from auth.users';
COMMENT ON FUNCTION langconnect.auto_create_user_role() IS 'Automatically creates user role when new user signs up via Supabase auth. First user gets dev_admin role.';
COMMENT ON FUNCTION langconnect.backfill_missing_user_roles_v2() IS 'Backfills user roles for existing users who signed up before the trigger was created. First user gets dev_admin role.';
COMMENT ON FUNCTION langconnect.auto_grant_public_permissions() IS 'Automatically grants public permissions to new users';
COMMENT ON FUNCTION langconnect.backfill_public_permissions() IS 'One-time backfill function to grant existing public permissions to all existing users';
COMMENT ON FUNCTION langconnect.create_notification(UUID, langconnect.notification_type, VARCHAR, VARCHAR, VARCHAR, UUID, VARCHAR, VARCHAR, TEXT) IS 'Create a new notification for permission sharing';
COMMENT ON FUNCTION langconnect.accept_notification(UUID) IS 'Accept a notification and grant the associated permission';
COMMENT ON FUNCTION langconnect.reject_notification(UUID) IS 'Reject a notification without granting permission';
COMMENT ON FUNCTION langconnect.cleanup_expired_notifications() IS 'Mark expired notifications as expired status';
COMMENT ON FUNCTION langconnect.compute_assistant_hash(TEXT, JSONB, JSONB, JSONB, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ) IS 'Compute stable hash of assistant fields for change detection';
COMMENT ON FUNCTION langconnect.compute_graph_hash(TEXT) IS 'Compute graph-level hash from aggregated assistant hashes';
COMMENT ON FUNCTION langconnect.increment_cache_version(TEXT) IS 'Atomically increment cache version for frontend invalidation';
COMMENT ON FUNCTION langconnect.upsert_assistant_mirror(UUID, TEXT, TEXT, JSONB, JSONB, JSONB, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ) IS 'Upsert assistant into mirror with change detection and version increment';
COMMENT ON FUNCTION langconnect.refresh_graph_mirror(TEXT) IS 'Refresh graph aggregations from assistants and increment version if changed';
COMMENT ON FUNCTION langconnect.upsert_assistant_schemas(UUID, JSONB, JSONB, JSONB) IS 'Upsert assistant schemas with change detection and version increment';
COMMENT ON FUNCTION langconnect.upsert_graph_schemas(TEXT, JSONB, JSONB, JSONB) IS 'Upsert graph schemas with change detection and version increment';
COMMENT ON FUNCTION langconnect.upsert_thread_mirror(UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ) IS 'Upsert thread metadata into mirror with proper name update handling';
COMMENT ON FUNCTION langconnect.update_job_progress(UUID, langconnect.job_status, INTEGER, VARCHAR, TEXT, JSONB) IS 'Update job progress with automatic timing calculations';
COMMENT ON FUNCTION langconnect.cleanup_old_jobs() IS 'Clean up completed/failed/cancelled jobs older than 30 days';
COMMENT ON FUNCTION langconnect.reassign_default_assistant_on_delete() IS 'Auto-reassigns user default assistant when current default is deleted. Prioritizes owned > editor > viewer assistants by most recent creation.';
COMMENT ON FUNCTION langconnect.check_default_on_permission_revoke() IS 'Checks and reassigns default assistant when user loses access to their current default. Prioritizes owned > editor > viewer assistants.';

-- Index comments
COMMENT ON INDEX langconnect.idx_embedding_document_lookup IS 'Optimizes queries that look up chunks by document within a specific collection';

-- Backfill existing users with roles and public permissions (from archived migrations)
DO $$
DECLARE
    backfilled_count INTEGER;
    graph_perms_granted INTEGER;
    assistant_perms_granted INTEGER;
    collection_perms_granted INTEGER;
BEGIN
    -- Backfill user roles for existing users
    SELECT langconnect.backfill_missing_user_roles_v2() INTO backfilled_count;
    RAISE NOTICE '✅ Backfilled % user roles for existing users', backfilled_count;
    
    -- Backfill public permissions for existing users
    SELECT graphs_granted, assistants_granted, collections_granted 
    FROM langconnect.backfill_public_permissions() 
    INTO graph_perms_granted, assistant_perms_granted, collection_perms_granted;
    RAISE NOTICE '✅ Backfilled % graph permissions, % assistant permissions, and % collection permissions for existing users', 
        graph_perms_granted, assistant_perms_granted, collection_perms_granted;
END $$;

-- Record this migration in lanconnect track
INSERT INTO langconnect.lanconnect_migration_versions (version, description)
VALUES ('001', 'Consolidated LAN Connect baseline schema')
ON CONFLICT (version) DO NOTHING;


