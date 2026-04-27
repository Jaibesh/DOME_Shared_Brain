"""
supabase_client.py — Supabase Python Client initialized with Service Role Key

Connects to the PostgreSQL database bypassing RLS, allowing unrestricted read/write
from the guaranteed-secure Railway FastAPI backend environment.
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None

def get_supabase() -> Client:
    """Initialize and retrieve the Supabase client (cached singleton)."""
    global _client
    if _client is not None:
        return _client
    
    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_KEY", "")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")
        
    # SUPABASE_KEY should ideally be the `service_role` key to bypass RLS securely from backend
    _client = create_client(supabase_url=url, supabase_key=key)
    return _client

