"""
supabase_helpers.py — Unified Supabase Client Factory for All Agents

Provides a singleton Supabase client that reads SUPABASE_URL / SUPABASE_KEY
from the environment. Replaces the 8+ inline create_client() calls scattered
across webhook processors, scripts, and helpers.

Usage:
    from shared.supabase_helpers import get_supabase
    sb = get_supabase()
    data = sb.table("reservations").select("*").execute()
"""

import os
from typing import Optional

_client = None


def get_supabase():
    """
    Get or create the singleton Supabase client.

    Reads SUPABASE_URL and SUPABASE_KEY from environment variables.
    Caches the client for the lifetime of the process.

    Returns:
        supabase.Client instance

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY are not set
        ImportError: If supabase-py is not installed
    """
    global _client
    if _client is not None:
        return _client

    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")

    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY must be set in environment variables.\n"
            "Check your agent's .env file."
        )

    _client = create_client(url, key)
    return _client


def reset_client():
    """Reset the cached client (useful for testing or credential rotation)."""
    global _client
    _client = None
