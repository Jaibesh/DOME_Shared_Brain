import sys, os

# DOME 2.2.2 / V3 Centralized Tether
CORE_PATH = os.environ.get("DOME_CORE_ROOT", r"D:\DOME_CORE")

if os.path.exists(CORE_PATH) and CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)

# Establish unique local ID for central registry integration
os.environ.setdefault("AGENT_ID", "epic_4x4_waiver_recon")
