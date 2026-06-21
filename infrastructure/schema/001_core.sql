-- Assest Core Schema — PostgreSQL Production DDL
-- Version: 001
-- Apply via: psql $DATABASE_URL -f infrastructure/schema/001_core.sql
-- Or migrate with Alembic/Flyway using this as baseline.

BEGIN;

-- ── Extensions ──────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Enums ───────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE connectortype AS ENUM (
        'notion', 'google_drive', 'slack', 'github', 'jira', 'whatsapp', 'file_upload'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE connectorstatus AS ENUM ('active', 'paused', 'error');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE feedbacktype AS ENUM ('positive', 'negative', 'null');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── Core Tables ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    supabase_id     TEXT UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT,
    full_name       TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_supabase_id ON users (supabase_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

CREATE TABLE IF NOT EXISTS workspaces (
    id          TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    settings    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces (slug);

CREATE TABLE IF NOT EXISTS workspace_members (
    id              TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members (user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace ON workspace_members (workspace_id);

CREATE TABLE IF NOT EXISTS connectors (
    id                  TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    workspace_id        TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    type                connectortype NOT NULL,
    config              JSONB NOT NULL DEFAULT '{}',
    status              connectorstatus NOT NULL DEFAULT 'active',
    last_synced_at      TIMESTAMPTZ,
    last_sync_cursor    TEXT,
    error_log           JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace ON connectors (workspace_id);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace_status ON connectors (workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_connectors_last_synced ON connectors (last_synced_at DESC);

CREATE TABLE IF NOT EXISTS documents (
    id                  TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    workspace_id        TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    connector_id        TEXT REFERENCES connectors(id) ON DELETE SET NULL,
    source_url          TEXT NOT NULL,
    title               TEXT,
    document_type       TEXT NOT NULL DEFAULT 'general',
    mime_type           TEXT,
    content_hash        TEXT NOT NULL,
    chunk_count         INTEGER NOT NULL DEFAULT 0,
    tier                INTEGER NOT NULL DEFAULT 2,
    tags                JSONB NOT NULL DEFAULT '[]',
    last_ingested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_stale            BOOLEAN NOT NULL DEFAULT FALSE,
    version             INTEGER NOT NULL DEFAULT 1,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    previous_version_id TEXT,
    UNIQUE (workspace_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents (workspace_id);
CREATE INDEX IF NOT EXISTS idx_documents_connector ON documents (connector_id);
CREATE INDEX IF NOT EXISTS idx_documents_active ON documents (workspace_id, is_active) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS chunks (
    id                  TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    document_id         TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    workspace_id        TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    parent_id           TEXT,
    heading_path        JSONB NOT NULL DEFAULT '[]',
    chunk_type          TEXT NOT NULL DEFAULT 'text',
    structural_metadata JSONB NOT NULL DEFAULT '{}',
    content             TEXT NOT NULL,
    content_tokens      INTEGER NOT NULL DEFAULT 0,
    chunk_index         INTEGER NOT NULL DEFAULT 0,
    search_content      TEXT,
    tier                INTEGER NOT NULL DEFAULT 2,
    source_type         TEXT,
    source_url          TEXT,
    document_title      TEXT,
    permissions         JSONB NOT NULL DEFAULT '{}',
    quality_score       DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    retrieval_count     INTEGER NOT NULL DEFAULT 0,
    positive_feedback   INTEGER NOT NULL DEFAULT 0,
    negative_feedback   INTEGER NOT NULL DEFAULT 0,
    source_modified_at  TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,
    version             INTEGER NOT NULL DEFAULT 1,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_workspace_active ON chunks (workspace_id, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts ON chunks USING GIN (to_tsvector('english', content));

CREATE TABLE IF NOT EXISTS conversations (
    id              TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title           TEXT NOT NULL DEFAULT 'New Conversation',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations (workspace_id);

CREATE TABLE IF NOT EXISTS query_logs (
    id                  TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    workspace_id        TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    conversation_id     TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    question            TEXT NOT NULL,
    answer              TEXT,
    sources             JSONB NOT NULL DEFAULT '[]',
    request_id          TEXT,
    feedback            feedbacktype NOT NULL DEFAULT 'null',
    response_time_ms    INTEGER,
    faithfulness_score  DOUBLE PRECISION,
    relevance_score     DOUBLE PRECISION,
    eval_reasoning      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_query_logs_workspace ON query_logs (workspace_id);
CREATE INDEX IF NOT EXISTS idx_query_logs_conversation ON query_logs (conversation_id);
CREATE INDEX IF NOT EXISTS idx_query_logs_created ON query_logs (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_logs_request_id ON query_logs (request_id);

CREATE TABLE IF NOT EXISTS background_tasks (
    id              TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    task_type       TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',
    retry_count     INTEGER NOT NULL DEFAULT 0,
    error_log       JSONB,
    stats           JSONB NOT NULL DEFAULT '{}',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_background_tasks_status ON background_tasks (status, created_at ASC)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_background_tasks_type ON background_tasks (task_type);

CREATE TABLE IF NOT EXISTS sync_runs (
    id              TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    connector_id    TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'queued',
    stats           JSONB NOT NULL DEFAULT '{}',
    error_log       JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sync_runs_connector ON sync_runs (connector_id, created_at DESC);

CREATE TABLE IF NOT EXISTS failed_ingestions (
    id              TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    connector_id    TEXT REFERENCES connectors(id) ON DELETE SET NULL,
    source_id       TEXT NOT NULL,
    error_message   TEXT,
    payload         JSONB NOT NULL DEFAULT '{}',
    retry_count     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_failed_ingestions_status ON failed_ingestions (status, created_at ASC)
    WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS audit_ledger (
    id              TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         TEXT REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    resource_id     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_ledger_workspace ON audit_ledger (workspace_id, created_at DESC);

COMMIT;
