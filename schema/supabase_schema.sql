-- ============================================================================
-- DOME 4.0 Supabase Schema
-- ============================================================================
-- Run this in your personal Supabase project's SQL Editor.
-- Requires: pgvector extension (enabled by default on Supabase)
-- ============================================================================

-- Enable pgvector for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. AGENT REGISTRY
-- Cloud-hosted registry replacing the empty local D:\DOME_CORE\registry\
-- ============================================================================
CREATE TABLE IF NOT EXISTS dome_agents (
    agent_id        TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    workspace_path  TEXT,
    environment     TEXT DEFAULT 'home',  -- 'home' or 'work'
    capabilities    TEXT[] DEFAULT '{}',
    tools           TEXT[] DEFAULT '{}',
    dome_version    TEXT DEFAULT '4.0',
    status          TEXT DEFAULT 'active' CHECK (status IN ('active', 'dormant', 'archived')),
    last_heartbeat  TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 2. MEMORY STORE (Mem0 Pattern)
-- Semantic vector memory with intelligent relevance decay
-- ============================================================================
CREATE TABLE IF NOT EXISTS dome_memories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL,
    content         TEXT NOT NULL,
    category        TEXT DEFAULT 'general',
    embedding       VECTOR(1536),  -- OpenAI text-embedding-3-small dimension
    tags            TEXT[] DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    relevance_score FLOAT DEFAULT 1.0,
    access_count    INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    accessed_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast semantic search
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
    ON dome_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for filtering
CREATE INDEX IF NOT EXISTS idx_memories_agent ON dome_memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_category ON dome_memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_tags ON dome_memories USING gin(tags);

-- ============================================================================
-- 3. KNOWLEDGE INSIGHTS (Structured Learning)
-- Replaces the local JSONL append-only logs
-- ============================================================================
CREATE TABLE IF NOT EXISTS dome_insights (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_agent    TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN (
        'optimization', 'compliance', 'user_pattern', 
        'error_fix', 'strategy', 'architecture', 'tool_creation'
    )),
    summary         TEXT NOT NULL,
    content         TEXT NOT NULL,
    tags            TEXT[] DEFAULT '{}',
    embedding       VECTOR(1536),
    superseded_by   UUID REFERENCES dome_insights(id),  -- For refutation/updates
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insights_embedding 
    ON dome_insights USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

CREATE INDEX IF NOT EXISTS idx_insights_category ON dome_insights(category);
CREATE INDEX IF NOT EXISTS idx_insights_author ON dome_insights(author_agent);

-- ============================================================================
-- 4. AUDIT LOG
-- Immutable trail of all significant DOME actions
-- ============================================================================
CREATE TABLE IF NOT EXISTS dome_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL,
    environment     TEXT DEFAULT 'home',
    action_type     TEXT NOT NULL,
    summary         TEXT NOT NULL,
    details         JSONB DEFAULT '{}',
    conversation_id TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_agent ON dome_audit_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON dome_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_created ON dome_audit_log(created_at DESC);

-- ============================================================================
-- 5. LANGGRAPH CHECKPOINTS
-- Persistent workflow state for cross-environment resume
-- ============================================================================
CREATE TABLE IF NOT EXISTS dome_checkpoints (
    thread_id               TEXT NOT NULL,
    checkpoint_id           TEXT NOT NULL,
    parent_checkpoint_id    TEXT,
    checkpoint              JSONB NOT NULL,
    metadata                JSONB DEFAULT '{}',
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON dome_checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created ON dome_checkpoints(created_at DESC);

-- ============================================================================
-- 6. TOOL REGISTRY
-- Tracks all MCP-compatible tools across the ecosystem
-- ============================================================================
CREATE TABLE IF NOT EXISTS dome_tools (
    tool_id         TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    description     TEXT,
    tool_type       TEXT DEFAULT 'python' CHECK (tool_type IN ('python', 'mcp', 'playwright', 'api')),
    source_path     TEXT,           -- Relative path in DOME_CORE repo
    input_schema    JSONB,          -- Pydantic/JSON schema for inputs
    output_schema   JSONB,          -- Pydantic/JSON schema for outputs
    registered_by   TEXT,           -- Agent that registered it
    version         TEXT DEFAULT '1.0.0',
    status          TEXT DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 7. HELPER FUNCTIONS
-- ============================================================================

-- Semantic search function for memories
CREATE OR REPLACE FUNCTION search_memories(
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5,
    filter_agent TEXT DEFAULT NULL,
    filter_category TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    agent_id TEXT,
    content TEXT,
    category TEXT,
    tags TEXT[],
    metadata JSONB,
    relevance_score FLOAT,
    similarity FLOAT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        m.id,
        m.agent_id,
        m.content,
        m.category,
        m.tags,
        m.metadata,
        m.relevance_score,
        1 - (m.embedding <=> query_embedding) AS similarity,
        m.created_at
    FROM dome_memories m
    WHERE 
        (filter_agent IS NULL OR m.agent_id = filter_agent)
        AND (filter_category IS NULL OR m.category = filter_category)
        AND m.relevance_score > 0.1  -- Skip effectively forgotten memories
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Semantic search function for insights
CREATE OR REPLACE FUNCTION search_insights(
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5,
    filter_category TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    author_agent TEXT,
    category TEXT,
    summary TEXT,
    content TEXT,
    tags TEXT[],
    similarity FLOAT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        i.id,
        i.author_agent,
        i.category,
        i.summary,
        i.content,
        i.tags,
        1 - (i.embedding <=> query_embedding) AS similarity,
        i.created_at
    FROM dome_insights i
    WHERE 
        (filter_category IS NULL OR i.category = filter_category)
        AND i.superseded_by IS NULL  -- Only return current insights
    ORDER BY i.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_agents_updated
    BEFORE UPDATE ON dome_agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_tools_updated
    BEFORE UPDATE ON dome_tools
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Memory access tracking (updates accessed_at and access_count)
CREATE OR REPLACE FUNCTION touch_memory(memory_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE dome_memories
    SET accessed_at = NOW(), access_count = access_count + 1
    WHERE id = memory_id;
END;
$$;

-- Relevance decay function (run periodically to "forget" stale memories)
CREATE OR REPLACE FUNCTION decay_stale_memories(decay_days INT DEFAULT 90)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    affected INT;
BEGIN
    UPDATE dome_memories
    SET relevance_score = GREATEST(0.1, relevance_score * 0.9)
    WHERE accessed_at < NOW() - (decay_days || ' days')::INTERVAL
      AND relevance_score > 0.1;
    
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$;
