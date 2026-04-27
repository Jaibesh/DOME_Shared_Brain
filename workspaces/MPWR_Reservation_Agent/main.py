"""
main.py — MPOWR Reservation Creator Daemon (Standalone)
"""
import os
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

from slack_notifier import SlackNotifier
from bot_logger import get_bot_logger
from mpowr_creator_bot import cleanup_old_screenshots, reap_playwright_zombies
from apscheduler.schedulers.blocking import BlockingScheduler

slack = SlackNotifier()
log = get_bot_logger()

def run_creator_safely():
    try:
        from webhook_processor import process_webhooks
        
        # DOME Heartbeat
        try:
            from core.supabase_client import heartbeat
            heartbeat("mpwr_creator")
        except Exception as e:
            log.warning(f"Failed to send DOME heartbeat: {e}")
            
        reap_playwright_zombies()
        cleanup_old_screenshots(max_age_days=7)
        process_webhooks()
    except Exception as e:
        print(f"Fatally unhandled outer loop error: {e}")

if __name__ == "__main__":
    print("MPOWR Automated System Initialized (Powered by APScheduler). Running indefinitely...")
    
    # DOME V4 Agent Registration
    try:
        from core.supabase_client import register_agent
        import inspect
        workspace_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        register_agent(
            agent_id="mpwr_creator",
            display_name="MPWR Reservation Creator Bot",
            workspace_path=workspace_path,
            capabilities=["webhook_processing", "mpowr_creation", "slack_notifications"],
            tools=["playwright", "supabase"]
        )
        print("[DOME] Agent registered to cloud registry.")
    except Exception as e:
        print(f"[DOME] Failed to register agent (non-critical): {e}")
    
    # Run once on boot to catch up
    print("Running initial boot sequence...")
    run_creator_safely()
    
    # Setup scheduler in Denver timezone
    tz = pytz.timezone('America/Denver')
    scheduler = BlockingScheduler(timezone=tz)
    
    # 1. Creator Bot - Real-Time Polling (Every 15 seconds)
    # The webhook_processor exits in <50ms if no webhooks exist.
    # APScheduler inherently prevents overlapping executions.
    scheduler.add_job(run_creator_safely, 'interval', seconds=15, id='creator_poll')
    
    print("[Scheduler] Automated agenda locked in.")
    print("  - MPOWR Creator: Every 15 seconds")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler safely stopped.")
