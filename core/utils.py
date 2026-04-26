
import os
import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional, Union

def get_dome_path() -> str:
    """
    Get the DOME_CORE root path with fallback hierarchy.
    Priority 1: Environment variable DOME_CORE_ROOT
    Priority 2: D:\DOME_CORE (primary spine)
    Priority 3: G:\DOME_CORE (sync drive)
    Priority 4: Return None (local mode)
    """
    # Check environment variable first
    env_path = os.environ.get("DOME_CORE_ROOT")
    if env_path and os.path.exists(env_path):
        return env_path
    
    # Check primary spine
    if os.path.exists(r"D:\DOME_CORE"):
        return r"D:\DOME_CORE"
    
    # Check sync drive
    if os.path.exists(r"G:\DOME_CORE"):
        return r"G:\DOME_CORE"
    
    # No centralized DOME found
    return None

def setup_global_paths():
    """Injects CNS core and tools into sys.path using DOME 2.2.2 path resolution."""
    dome_root = get_dome_path()
    if dome_root:
        paths = [
            dome_root,  # Add root for 'from core import ...'
            os.path.join(dome_root, "core"),
            os.path.join(dome_root, "tools")
        ]
        for p in paths:
            if p not in sys.path:
                sys.path.insert(0, p)  # Insert at beginning for priority

def ensure_directory(path: str):
    if not os.path.exists(path):
        os.makedirs(path)

def save_json(filepath: str, data: Any):
    ensure_directory(os.path.dirname(filepath))
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_json(filepath: str, default: Any = None) -> Any:
    if not os.path.exists(filepath):
        return default if default is not None else {}
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def clean_filename(text: str) -> str:
    return "".join([c for c in text if c.isalnum() or c in (' ', '_', '-')]).rstrip().replace(' ', '_')
