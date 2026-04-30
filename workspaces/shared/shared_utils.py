"""
shared_utils.py — Common utility functions shared across all agents.

Consolidates duplicated logic that was previously copy-pasted into each agent.
"""

import os
import subprocess
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


def cleanup_old_files(directory: str, pattern: str = "*.png", max_age_days: int = 3) -> int:
    """Remove files matching a pattern from a directory if older than max_age_days.
    
    More generic than cleanup_screenshots — works on any directory and any extension.
    Useful for cleaning up debug screenshots, log dumps, etc.
    
    Args:
        directory: Directory to clean
        pattern: Glob pattern to match files (default: *.png)
        max_age_days: Maximum age of files to keep (default: 3)
        
    Returns:
        Number of files removed
    """
    import fnmatch
    if not os.path.exists(directory):
        return 0
    cutoff = datetime.now().timestamp() - (max_age_days * 86400)
    removed = 0
    for fname in os.listdir(directory):
        if not fnmatch.fnmatch(fname, pattern):
            continue
        fpath = os.path.join(directory, fname)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
            try:
                os.remove(fpath)
                removed += 1
            except OSError:
                pass
    return removed


def reap_playwright_zombies() -> None:
    """Kill lingering headless browser processes spawned by Playwright.
    
    Prevents zombie Chromium/Edge processes from consuming system RAM if an agent
    crashes or is force-quit. Specifically targets processes with 'ms-playwright'
    in their launch path to avoid killing the user's personal browser sessions.
    
    Safe to call from any agent — uses PowerShell and is Windows-specific.
    Silently does nothing if called on non-Windows or if no zombies are found.
    """
    if os.name != "nt":
        return  # Only relevant on Windows
        
    script = (
        "Get-CimInstance Win32_Process -Filter "
        "\"Name = 'msedge.exe' OR Name = 'chrome.exe' OR Name = 'chromium.exe'\" "
        "| Where-Object {$_.ExecutablePath -match 'ms-playwright'} "
        "| Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass  # Non-critical — don't crash the agent over cleanup
