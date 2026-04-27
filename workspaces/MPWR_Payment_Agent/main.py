import os
from dotenv import load_dotenv

# Load environment variables FIRST, before importing local modules that might read them on initialization
load_dotenv()

import time
from apscheduler.schedulers.blocking import BlockingScheduler
from bot_logger import get_bot_logger
from webhook_processor import process_payment_webhooks
from deposit_checker import check_upcoming_deposits
from slack_notifier import slack

log = get_bot_logger()

def safe_webhook_job():
    log.info("--- Starting Webhook Processing Cycle ---")
    try:
        # DOME Heartbeat
        try:
            from core.supabase_client import heartbeat
            heartbeat("mpwr_payment")
        except Exception:
            pass
            
        process_payment_webhooks()
    except Exception as e:
        log.error(f"Error in webhook processor job: {e}")
        slack.send_message(f"❌ Payment Agent Webhook Job Failed: {e}")
    log.info("--- Webhook Cycle Complete ---")

def safe_deposit_job():
    log.info("--- Starting Deposit Checking Cycle ---")
    try:
        check_upcoming_deposits()
    except Exception as e:
        log.error(f"Error in deposit checking job: {e}")
        slack.send_message(f"❌ Payment Agent Deposit Job Failed: {e}")
    log.info("--- Deposit Cycle Complete ---")

def main():
    log.info("Booting up MPWR Payment Agent...")
    
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        log.error("CRITICAL: SUPABASE_URL or SUPABASE_KEY is not set.")
        return

    if not os.getenv("MPOWR_EMAIL") or not os.getenv("MPOWR_PASSWORD"):
        log.error("CRITICAL: MPOWR credentials are not set.")
        return

    slack.send_message("🚀 MPWR Payment Agent is starting up...")

    # DOME V4 Agent Registration
    try:
        from core.supabase_client import register_agent
        import inspect
        workspace_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        register_agent(
            agent_id="mpwr_payment",
            display_name="MPWR Payment Agent",
            workspace_path=workspace_path,
            capabilities=["webhook_processing", "deposit_collection", "payment_settlement"],
            tools=["playwright", "supabase"]
        )
        log.info("[DOME] Agent registered to cloud registry.")
    except Exception as e:
        log.warning(f"[DOME] Failed to register agent (non-critical): {e}")

    # Run jobs once on boot
    safe_webhook_job()
    safe_deposit_job()

    scheduler = BlockingScheduler(timezone="America/Denver")

    # Schedule webhook processing every 5 minutes
    scheduler.add_job(
        safe_webhook_job,
        "interval",
        minutes=5,
        id="webhook_processor_job",
        replace_existing=True
    )

    # Schedule deposit checking every 5 minutes
    scheduler.add_job(
        safe_deposit_job,
        "interval",
        minutes=5,
        id="deposit_checker_job",
        replace_existing=True
    )

    try:
        log.info("Starting APScheduler loop. Press Ctrl+C to exit.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down MPWR Payment Agent...")
        slack.send_message("🛑 MPWR Payment Agent shutting down.")

if __name__ == "__main__":
    main()
