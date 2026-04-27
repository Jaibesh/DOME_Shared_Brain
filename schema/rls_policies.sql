-- ============================================================================
-- DOME 4.0 — Row Level Security Policies
-- ============================================================================
-- Run this AFTER the main schema to allow the anon key full access.
-- This is safe because this is a PERSONAL project, not multi-tenant.
-- ============================================================================

-- dome_agents: allow all operations
ALTER TABLE dome_agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access to dome_agents" ON dome_agents
    FOR ALL USING (true) WITH CHECK (true);

-- dome_memories: allow all operations
ALTER TABLE dome_memories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access to dome_memories" ON dome_memories
    FOR ALL USING (true) WITH CHECK (true);

-- dome_insights: allow all operations
ALTER TABLE dome_insights ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access to dome_insights" ON dome_insights
    FOR ALL USING (true) WITH CHECK (true);

-- dome_audit_log: allow all operations
ALTER TABLE dome_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access to dome_audit_log" ON dome_audit_log
    FOR ALL USING (true) WITH CHECK (true);

-- dome_checkpoints: allow all operations
ALTER TABLE dome_checkpoints ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access to dome_checkpoints" ON dome_checkpoints
    FOR ALL USING (true) WITH CHECK (true);

-- dome_tools: allow all operations
ALTER TABLE dome_tools ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access to dome_tools" ON dome_tools
    FOR ALL USING (true) WITH CHECK (true);
