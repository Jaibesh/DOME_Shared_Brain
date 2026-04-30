import os
import sys
import time
from datetime import datetime
from pytz import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# CRITICAL: Load .env BEFORE importing modules that create SlackNotifier singletons.
load_dotenv()

# Add shared modules
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared"))
from supabase_client import get_supabase
from slack_notifier import SlackNotifier

from mpowr_return_bot import MpowrReturnBot

AGENT_NAME = "MPWR_Return_Agent"
POLL_INTERVAL_MINS = 60

slack = SlackNotifier(AGENT_NAME)
MDT = timezone("America/Denver")

def check_tour_returns():
    """Polls MPOWR to check if today's tours are completed."""
    now = datetime.now(MDT)
    
    # Only run between 8:00 AM and 8:00 PM
    if now.hour < 8 or now.hour >= 20:
        print(f"[{now.strftime('%I:%M %p')}] Outside operating hours (8AM - 8PM). Skipping.")
        return

    print(f"\n[{now.strftime('%H:%M:%S')}] --- Checking Tour Returns ---")
    
    today_str = now.strftime("%Y-%m-%d")
    supabase = get_supabase()
    
    # 1. Fetch today's tours from Supabase that are NOT returned yet
    try:
        resp = supabase.table("reservations") \
            .select("tw_confirmation, mpwr_number, guest_name, tw_status, rental_status") \
            .eq("booking_type", "Tour") \
            .neq("rental_status", "Returned") \
            .neq("rental_status", "Completed") \
            .eq("activity_date", today_str) \
            .execute()
        tours = resp.data
    except Exception as e:
        print(f"Supabase error: {e}")
        slack._send_message(None, f"❌ Supabase error fetching tours: {e}")
        return

    if not tours:
        print("No open tours found for today. All good.")
        return
        
    print(f"Found {len(tours)} open tours for today. Checking MPOWR...")

    bot = None
    try:
        bot = MpowrReturnBot()
        
        for t in tours:
            tw_conf = t.get("tw_confirmation")
            mpwr_id = t.get("mpwr_number")
            name = t.get("guest_name")
            
            if not mpwr_id or mpwr_id == "0":
                continue
                
            print(f"Checking MPOWR #{mpwr_id} for {name} ({tw_conf})...")
            status = bot.get_reservation_status(mpwr_id)
            
            if status and status.lower() in ("completed", "returned"):
                print(f"  -> ✅ MPOWR status is '{status}'. Updating database.")
                try:
                    supabase.table("reservations") \
                        .update({"rental_status": "Completed"}) \
                        .eq("tw_confirmation", tw_conf) \
                        .execute()
                    
                    slack._send_message(None, f"🚙 *Tour Completed:* {name} (MPOWR #{mpwr_id} | TW: {tw_conf}). Removed from Dashboard.")
                except Exception as e:
                    print(f"  -> ❌ Failed to update Supabase: {e}")
            else:
                print(f"  -> ⏳ MPOWR status is '{status}'. Tour still active.")

    except Exception as e:
        print(f"Error checking returns: {e}")
        slack._send_message(None, f"❌ Return Agent error: {e}")
    finally:
        if bot:
            bot.close()


if __name__ == "__main__":
    print(f"[{AGENT_NAME}] Starting Tour Sync Daemon (Runs hourly from 8AM-8PM)...")
    
    # Run immediately on startup to test
    check_tour_returns()
    
    scheduler = BackgroundScheduler()
    # Run at the top of every hour
    scheduler.add_job(check_tour_returns, 'cron', minute=0)
    scheduler.start()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print(f"\n[{AGENT_NAME}] Shutting down.")
