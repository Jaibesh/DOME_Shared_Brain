import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Add workspaces directory to sys.path to import shared modules
WORKSPACE_DIR = Path(__file__).parent.parent
sys.path.append(str(WORKSPACE_DIR))

from shared.bot_logger import get_bot_logger
from shared.slack_notifier import SlackNotifier
from service_bot import ServiceBot

log = get_bot_logger("service_main", str(Path(__file__).parent / "logs"))
slack = SlackNotifier("Service_Work_Order_Agent")

def run_job(is_manual_run=False):
    log.info("=== Starting Daily Service Work Order Job ===")
    email = os.environ.get("MPOWR_EMAIL")
    password = os.environ.get("MPOWR_PASSWORD")
    
    if not email or not password:
        msg = "Missing MPOWR_EMAIL or MPOWR_PASSWORD in .env"
        log.error(msg)
        slack.send_error_alert(msg)
        return
        
    bot = ServiceBot(headless=not is_manual_run) # Show browser if running manually
    
    try:
        bot.start()
        bot.run_daily_workflow(email, password)
        # slack.send_success_alert("Successfully completed daily Service Work Order job.")
        log.info("=== Daily Service Work Order Job Completed ===")
    except Exception as e:
        msg = f"Service Work Order Agent failed: {e}"
        log.error(msg)
        slack.send_error_alert(msg)
    finally:
        bot.stop()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Service Work Order Agent")
    parser.add_argument("--now", action="store_true", help="Run immediately instead of scheduling")
    args = parser.parse_args()

    if args.now:
        run_job(is_manual_run=True)
    else:
        from apscheduler.schedulers.blocking import BlockingScheduler
        
        log.info("Starting Service Work Order Agent Scheduler...")
        scheduler = BlockingScheduler()
        
        # Schedule the job to run every day at 8:00 AM
        scheduler.add_job(run_job, 'cron', hour=8, minute=0)
        
        log.info("Scheduler configured. Running initial startup job...")
        
        # Run once immediately on startup
        run_job(is_manual_run=False)
        
        log.info("Initial startup job complete. Scheduler is now waiting for next 08:00 AM...")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped.")
