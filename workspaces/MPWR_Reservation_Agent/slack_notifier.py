"""slack_notifier.py — Thin wrapper delegating to shared module.
Edit shared/slack_notifier.py instead of this file."""
import sys, os
_ws = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
if _ws not in sys.path: sys.path.insert(0, _ws)
from shared.slack_notifier import SlackNotifier

# Agent-specific singleton (preserves existing `from slack_notifier import slack` usage)
slack = SlackNotifier(agent_name="mpwr_creator")
