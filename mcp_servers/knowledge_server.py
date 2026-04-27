"""
DOME 4.0 — Knowledge MCP Server
=================================
Exposes DOME's cloud memory and knowledge capabilities as MCP tools.

Any AI IDE (Cursor, VS Code, Claude Desktop, Gemini Code Assist) can
discover and call these tools natively.

Tools Exposed:
- search_memory: Semantic search across DOME cloud memory
- add_memory: Store a new memory in the cloud brain
- search_insights: Search structured insights
- log_insight: Log a new structured insight
- list_agents: List all registered DOME agents
- system_status: Get DOME system health status

Run:
    python -m mcp_servers.knowledge_server
    
    Or configure in your IDE's MCP settings:
    {
        "mcpServers": {
            "dome-knowledge": {
                "command": "python",
                "args": ["-m", "mcp_servers.knowledge_server"],
                "cwd": "D:\\DOME_CORE"
            }
        }
    }
"""

import os
import sys

# Ensure DOME_CORE is on path
DOME_ROOT = os.environ.get("DOME_CORE_ROOT", r"D:\DOME_CORE")
sys.path.insert(0, DOME_ROOT)

# Load .env
env_path = os.path.join(DOME_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

from mcp.server.fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP(
    "DOME Knowledge",
    instructions="DOME 4.0 Cloud Memory & Knowledge — Search, store, and manage the shared agentic brain."
)


# =============================================================================
# MEMORY TOOLS
# =============================================================================

@mcp.tool()
def search_memory(query: str, category: str = "", limit: int = 5) -> str:
    """
    Search DOME's cloud memory semantically.
    
    Finds relevant memories across all agents and environments (home & work).
    Uses pgvector cosine similarity when embeddings are available,
    falls back to keyword search otherwise.
    
    Args:
        query: Natural language search query
        category: Optional category filter (general, optimization, error_fix, etc.)
        limit: Max results to return (default 5)
    """
    from core.memory_client import get_memory_client
    client = get_memory_client("mcp_user")
    results = client.search(query, limit=limit, category=category or None)
    
    if not results:
        return f"No memories found for: '{query}'"
    
    output = [f"Found {len(results)} memory/memories:\n"]
    for i, r in enumerate(results, 1):
        content = r.get("content", "")
        cat = r.get("category", "unknown")
        agent = r.get("agent_id", "unknown")
        score = r.get("similarity", r.get("relevance_score", "N/A"))
        tags = ", ".join(r.get("tags", []))
        output.append(f"{i}. [{cat}] {content}")
        output.append(f"   Agent: {agent} | Score: {score} | Tags: {tags}")
    
    return "\n".join(output)


@mcp.tool()
def add_memory(content: str, category: str = "general", tags: str = "") -> str:
    """
    Store a new memory in DOME's cloud brain.
    
    Memories persist across sessions and environments. They can be
    recalled later via semantic search.
    
    Args:
        content: The memory content to store
        category: Category (general, optimization, error_fix, strategy, architecture, tool_creation)
        tags: Comma-separated tags for filtering
    """
    from core.memory_client import get_memory_client
    client = get_memory_client("mcp_user")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    memory_id = client.add(content, category=category, tags=tag_list)
    return f"Memory stored successfully. ID: {memory_id}"


@mcp.tool()
def search_insights(query: str, category: str = "") -> str:
    """
    Search DOME's structured insight database.
    
    Insights are curated learnings from past work — optimizations,
    error fixes, architectural decisions, etc.
    
    Args:
        query: Natural language search query
        category: Optional filter (optimization, compliance, user_pattern, error_fix, strategy, architecture, tool_creation)
    """
    from core.memory_client import get_memory_client
    client = get_memory_client("mcp_user")
    results = client.search_insights(query, category=category or None)
    
    if not results:
        return f"No insights found for: '{query}'"
    
    output = [f"Found {len(results)} insight(s):\n"]
    for i, r in enumerate(results, 1):
        summary = r.get("summary", "")
        content = r.get("content", "")
        cat = r.get("category", "unknown")
        author = r.get("author_agent", "unknown")
        output.append(f"{i}. [{cat}] {summary}")
        output.append(f"   {content[:200]}")
        output.append(f"   Author: {author}")
    
    return "\n".join(output)


@mcp.tool()
def log_insight(category: str, summary: str, content: str, tags: str = "") -> str:
    """
    Log a structured insight to DOME's knowledge base.
    
    Use this when you discover something worth remembering:
    optimizations, bug fixes, architectural patterns, etc.
    
    Args:
        category: One of: optimization, compliance, user_pattern, error_fix, strategy, architecture, tool_creation
        summary: Brief one-line summary
        content: Full insight content
        tags: Comma-separated tags
    """
    from core.memory_client import get_memory_client
    client = get_memory_client("mcp_user")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    insight_id = client.log_insight(category, summary, content, tags=tag_list)
    return f"Insight logged. ID: {insight_id}"


# =============================================================================
# AGENT REGISTRY TOOLS
# =============================================================================

@mcp.tool()
def list_agents() -> str:
    """
    List all registered DOME agents across all environments.
    
    Shows agent IDs, environments (home/work), capabilities, and last heartbeat.
    """
    from core.supabase_client import get_supabase
    sb = get_supabase()
    result = sb.table("dome_agents").select("*").order("last_heartbeat", desc=True).execute()
    
    if not result.data:
        return "No agents registered."
    
    output = [f"Registered DOME Agents ({len(result.data)}):\n"]
    for agent in result.data:
        name = agent.get("display_name", agent.get("agent_id"))
        env = agent.get("environment", "unknown")
        status = agent.get("status", "unknown")
        caps = ", ".join(agent.get("capabilities", []))
        heartbeat = agent.get("last_heartbeat", "never")
        output.append(f"  {name} ({env})")
        output.append(f"    Status: {status} | Last seen: {heartbeat}")
        output.append(f"    Capabilities: {caps or 'none listed'}")
    
    return "\n".join(output)


@mcp.tool()
def system_status() -> str:
    """
    Get DOME 4.0 system health status.
    
    Shows Supabase connectivity, environment, agent count,
    memory count, and checkpoint count.
    """
    from core.supabase_client import get_supabase, get_environment, check_connection
    
    conn = check_connection()
    
    if not conn["connected"]:
        return f"DOME Status: OFFLINE\nError: {conn['error']}"
    
    sb = get_supabase()
    
    # Count records
    agents = sb.table("dome_agents").select("agent_id", count="exact").execute()
    memories = sb.table("dome_memories").select("id", count="exact").execute()
    insights = sb.table("dome_insights").select("id", count="exact").execute()
    checkpoints = sb.table("dome_checkpoints").select("thread_id", count="exact").execute()
    
    return (
        f"DOME 4.0 System Status\n"
        f"=====================\n"
        f"Environment:  {get_environment()}\n"
        f"Supabase:     CONNECTED\n"
        f"Agents:       {agents.count or 0}\n"
        f"Memories:     {memories.count or 0}\n"
        f"Insights:     {insights.count or 0}\n"
        f"Checkpoints:  {checkpoints.count or 0}\n"
        f"DOME Version: 4.0"
    )


# =============================================================================
# AUDIT TOOLS
# =============================================================================

@mcp.tool()
def recent_activity(limit: int = 10) -> str:
    """
    Show recent DOME activity from the audit log.
    
    Args:
        limit: Number of recent entries to show (default 10)
    """
    from core.supabase_client import get_supabase
    sb = get_supabase()
    result = sb.table("dome_audit_log").select("*").order(
        "created_at", desc=True
    ).limit(limit).execute()
    
    if not result.data:
        return "No recent activity."
    
    output = [f"Recent DOME Activity ({len(result.data)} entries):\n"]
    for entry in result.data:
        agent = entry.get("agent_id", "unknown")
        action = entry.get("action_type", "unknown")
        summary = entry.get("summary", "")
        env = entry.get("environment", "?")
        timestamp = entry.get("created_at", "?")
        output.append(f"  [{timestamp[:19]}] [{env}] {agent}: {action}")
        output.append(f"    {summary}")
    
    return "\n".join(output)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    mcp.run()
