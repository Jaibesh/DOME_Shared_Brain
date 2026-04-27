"""
DOME 4.0 - Supabase Client
===========================
Unified connection manager for the cloud-hosted DOME brain.
Handles authentication, connection pooling, and environment detection.

Usage:
    from core.supabase_client import get_supabase, get_environment

    sb = get_supabase()
    data = sb.table("dome_memories").select("*").execute()
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("dome.supabase")

# ---------------------------------------------------------------------------
# Lazy import: supabase-py is only required when cloud features are used
# ---------------------------------------------------------------------------
_supabase_module = None

def _ensure_supabase():
    """Lazy import of supabase to avoid hard dependency for local-only usage."""
    global _supabase_module
    if _supabase_module is None:
        try:
            import supabase
            _supabase_module = supabase
        except ImportError:
            raise ImportError(
                "supabase-py is required for DOME 4.0 cloud features. "
                "Install it with: pip install supabase"
            )
    return _supabase_module


# ---------------------------------------------------------------------------
# Environment Detection
# ---------------------------------------------------------------------------
def get_environment() -> str:
    """
    Detect which environment we're running in.
    Returns 'home', 'work', or 'unknown'.
    
    Detection priority:
    1. DOME_ENVIRONMENT env var (explicit override)
    2. DOME_CORE_ROOT path heuristic (D: = home, else = work)
    3. COMPUTERNAME / hostname
    """
    # Explicit override
    env = os.environ.get("DOME_ENVIRONMENT", "").lower()
    if env in ("home", "work"):
        return env
    
    # Path heuristic
    dome_root = os.environ.get("DOME_CORE_ROOT", "")
    if dome_root.startswith("D:"):
        return "home"
    
    # Hostname heuristic (customize these to your machine names)
    hostname = os.environ.get("COMPUTERNAME", "").lower()
    home_hostnames = os.environ.get("DOME_HOME_HOSTNAMES", "").lower().split(",")
    if hostname and hostname in home_hostnames:
        return "home"
    
    # Default
    return "work" if not os.path.exists(r"D:\DOME_CORE") else "home"


# ---------------------------------------------------------------------------
# Supabase Client Factory
# ---------------------------------------------------------------------------
_supabase_client_cache = None

def get_supabase():
    """
    Get or create the singleton Supabase client.
    
    Uses a module-level cache instead of @lru_cache so connection
    failures don't get permanently cached.
    
    Required environment variables:
        DOME_SUPABASE_URL   - Your Supabase project URL
        DOME_SUPABASE_KEY   - Your Supabase anon/service key
    
    Returns:
        supabase.Client instance
    
    Raises:
        ValueError: If required environment variables are not set
        ImportError: If supabase-py is not installed
    """
    global _supabase_client_cache
    if _supabase_client_cache is not None:
        return _supabase_client_cache
    
    supabase = _ensure_supabase()
    
    url = os.environ.get("DOME_SUPABASE_URL")
    key = os.environ.get("DOME_SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError(
            "DOME 4.0 requires Supabase credentials.\n"
            "Set the following environment variables:\n"
            "  DOME_SUPABASE_URL=https://your-project.supabase.co\n"
            "  DOME_SUPABASE_KEY=your-anon-key\n\n"
            "Get these from: https://supabase.com/dashboard → Settings → API"
        )
    
    client = supabase.create_client(url, key)
    _supabase_client_cache = client
    logger.info(f"[DOME 4.0] Supabase connected: {url[:40]}... (env: {get_environment()})")
    return client


def check_connection() -> dict:
    """
    Verify Supabase connectivity and return status info.
    
    Returns:
        dict with 'connected', 'environment', 'url', and 'error' keys
    """
    try:
        client = get_supabase()
        # Simple health check: query agent registry
        result = client.table("dome_agents").select("agent_id", count="exact").limit(1).execute()
        return {
            "connected": True,
            "environment": get_environment(),
            "url": os.environ.get("DOME_SUPABASE_URL", "")[:40] + "...",
            "agent_count": result.count if result.count else 0,
            "error": None
        }
    except Exception as e:
        return {
            "connected": False,
            "environment": get_environment(),
            "url": os.environ.get("DOME_SUPABASE_URL", "N/A"),
            "agent_count": 0,
            "error": str(e)
        }


# ---------------------------------------------------------------------------
# Agent Registration
# ---------------------------------------------------------------------------
def register_agent(
    agent_id: str,
    display_name: str,
    workspace_path: str = "",
    capabilities: list = None,
    tools: list = None
) -> dict:
    """
    Register or update an agent in the cloud registry.
    Called during dome_init to announce presence.
    """
    from datetime import datetime, timezone
    
    client = get_supabase()
    data = {
        "agent_id": agent_id,
        "display_name": display_name,
        "workspace_path": workspace_path,
        "environment": get_environment(),
        "capabilities": capabilities or [],
        "tools": tools or [],
        "dome_version": "4.0",
        "status": "active",
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
    }
    
    result = client.table("dome_agents").upsert(data).execute()
    logger.info(f"[DOME 4.0] Agent registered: {agent_id} ({get_environment()})")
    return result.data[0] if result.data else data


def heartbeat(agent_id: str) -> None:
    """Send a heartbeat to indicate this agent is alive."""
    from datetime import datetime, timezone
    
    try:
        client = get_supabase()
        client.table("dome_agents").update({
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "environment": get_environment(),
            "status": "active"
        }).eq("agent_id", agent_id).execute()
    except Exception as e:
        logger.warning(f"Heartbeat failed for {agent_id}: {e}")


# ---------------------------------------------------------------------------
# Audit Logging
# ---------------------------------------------------------------------------
def log_audit(
    agent_id: str,
    action_type: str,
    summary: str,
    details: dict = None,
    conversation_id: str = None
) -> None:
    """
    Log an action to the cloud audit trail.
    This replaces the local global_audit.jsonl file.
    Fails silently to never block the calling workflow.
    """
    try:
        client = get_supabase()
        client.table("dome_audit_log").insert({
            "agent_id": agent_id,
            "environment": get_environment(),
            "action_type": action_type,
            "summary": summary,
            "details": details or {},
            "conversation_id": conversation_id
        }).execute()
    except Exception as e:
        logger.warning(f"Audit log failed (non-critical): {e}")
