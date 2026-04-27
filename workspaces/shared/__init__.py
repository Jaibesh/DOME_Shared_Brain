"""
shared/__init__.py — DOME V4 Tethered Shared Module Package

Provides the sys.path setup so all workspace agents can:
  1. Import from this shared/ package (bot_logger, mpowr_login, slack_notifier, supabase_helpers)
  2. Import from DOME core (core.supabase_client, core.memory_client) when available

Usage from any agent's main.py:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from shared.bot_logger import get_bot_logger
    from shared.mpowr_login import login_to_mpowr
    from shared.slack_notifier import SlackNotifier
"""

import sys
import os

# ── DOME Core Tether ──────────────────────────────────────────────────────
# Makes `from core.supabase_client import ...` available to all agents
CORE_PATH = os.environ.get("DOME_CORE_ROOT", r"C:\DOME_CORE")
if os.path.exists(CORE_PATH) and CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)

# ── Shared utilities (re-export for convenience) ──────────────────────────
from shared.shared_utils import cleanup_screenshots
