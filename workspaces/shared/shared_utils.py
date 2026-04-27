"""
shared_utils.py — Common utility functions shared across all agents.

Consolidates duplicated logic that was previously copy-pasted into each agent.
"""

import os
from datetime import datetime


def cleanup_screenshots(base_dir: str, max_age_days: int = 7) -> int:
    """Remove screenshot files older than max_age_days.
    
    Args:
        base_dir: Directory containing the screenshots/ folder
        max_age_days: Maximum age of screenshots to keep
        
    Returns:
        Number of files removed
    """
    screenshots_dir = os.path.join(base_dir, "screenshots")
    if not os.path.exists(screenshots_dir):
        return 0
    cutoff = datetime.now().timestamp() - (max_age_days * 86400)
    removed = 0
    for fname in os.listdir(screenshots_dir):
        fpath = os.path.join(screenshots_dir, fname)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
            try:
                os.remove(fpath)
                removed += 1
            except OSError:
                pass
    return removed
