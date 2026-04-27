"""mpowr_login.py — Thin wrapper delegating to shared module.
Edit shared/mpowr_login.py instead of this file."""
import sys, os
_ws = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
if _ws not in sys.path: sys.path.insert(0, _ws)
from shared.mpowr_login import login_to_mpowr, MpowrLoginError
