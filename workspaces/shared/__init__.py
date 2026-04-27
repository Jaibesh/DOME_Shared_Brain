"""
shared/ — Common utilities shared across all Waiver System agents.

This package contains modules that are duplicated across multiple agents.
Each agent should add this directory to sys.path to import shared modules.

Usage from any agent:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
    from shared_utils import cleanup_screenshots
"""
