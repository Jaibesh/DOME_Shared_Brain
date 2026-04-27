"""
main.py — MPWR Update & Cancel Agent Daemon

Runs continuously in the background, polling the `update_webhooks` and
`cancel_webhooks` tables in Supabase. When it finds pending webhooks,
it triggers the webhook_processor to handle them.
"""

import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

from webhook_processor import process_webhooks
from bot_logger import get_bot_logger

load_dotenv()
log = get_bot_logger()

# Check for required .env vars
REQUIRED_VARS = ["MPOWR_EMAIL", "MPOWR_PASSWORD", "SUPABASE_URL", "SUPABASE_KEY", "SLACK_WEBHOOK_URL"]
missing = [v for v in REQUIRED_VARS if not os.getenv(v) or os.getenv(v) == "user_will_provide"]
if missing:
    print(f"❌ ERROR: Missing required .env variables: {', '.join(missing)}")
    print("Please populate the .env file before running the agent.")
    sys.exit(1)

POLL_INTERVAL_SECONDS = 15

def _cleanup_screenshots(max_age_days: int = 7):
    """Remove old screenshot files to prevent unbounded disk growth."""
    screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
    if not os.path.exists(screenshots_dir):
        return
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
    if removed:
        log.info(f"[Startup] Cleaned up {removed} old screenshot(s).")

def run_daemon():
    log.info("======================================================")
    log.info("🚀 Starting MPWR Update & Cancel Agent Daemon")
    log.info(f"Polling Interval: {POLL_INTERVAL_SECONDS} seconds")
    log.info("======================================================")

    # Cleanup old screenshots on startup
    _cleanup_screenshots()

    while True:
        try:
            # The processor handles both update and cancel queues
            process_webhooks()
        except Exception as e:
            log.error(f"[Daemon] Unexpected error in polling loop: {e}")
            import traceback
            log.error(traceback.format_exc())

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        run_daemon()
    except KeyboardInterrupt:
        log.info("🛑 Daemon stopped by user.")
        sys.exit(0)
