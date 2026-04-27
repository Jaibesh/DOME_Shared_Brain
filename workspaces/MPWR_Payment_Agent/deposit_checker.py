import os
from dotenv import load_dotenv

load_dotenv()

import time
import datetime
import re
from supabase import create_client, Client
from playwright.sync_api import sync_playwright, Page
from bot_logger import get_bot_logger
from slack_notifier import slack
from mpowr_login import login_to_mpowr
from pytz import timezone

log = get_bot_logger()

_supabase_client = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        _supabase_client = create_client(url, key)
    return _supabase_client

def get_today_str(tz_name="America/Denver"):
    tz = timezone(tz_name)
    now = datetime.datetime.now(tz)
    return now.strftime("%Y-%m-%d")

_alerted_deposits = set()

def check_upcoming_deposits():
    """
    Finds rentals within 30 mins of departure that need a deposit.
    Logs into MPOWR, checks "Payment Authorizations", and alerts if "On Ride" without auth.
    """
    global _alerted_deposits
    
    # Optional: Clear the set at midnight if we want to reset daily, 
    # but the process usually restarts often anyway.

    log.info("Starting deposit check cycle...")
    supabase = get_supabase()
    today_str = get_today_str()

    try:
        # Fetch all un-paid deposits for today's rentals with Standard Protection
        resp = supabase.table("reservations") \
            .select("tw_confirmation, mpwr_number, vehicle_qty, activity_time") \
            .eq("booking_type", "Rental") \
            .eq("adventure_assure", "AdventureAssure Standard Protection") \
            .neq("deposit_status", "Collected") \
            .neq("deposit_status", "Compensated") \
            .eq("activity_date", today_str) \
            .execute()
        
        records = resp.data
    except Exception as e:
        log.error(f"Failed to query Supabase for deposits: {e}")
        return

    if not records:
        log.info("No pending deposits for today's rentals.")
        return

    tz = timezone("America/Denver")
    now = datetime.datetime.now(tz)

    to_check = []
    for r in records:
        # parse activity_time e.g., "8:00 AM" or "2:00 PM"
        time_str = r.get("activity_time")
        if not time_str: continue
        try:
            dt_time = datetime.datetime.strptime(time_str.strip(), "%I:%M %p").time()
            dt_combined = tz.localize(datetime.datetime.combine(now.date(), dt_time))
            time_diff = (dt_combined - now).total_seconds() / 60.0
            
            # If within 30 mins or already past time (and still not paid)
            if time_diff <= 30:
                to_check.append(r)
        except Exception as e:
            log.warning(f"Could not parse time '{time_str}' for {r.get('tw_confirmation')}: {e}")

    if not to_check:
        log.info("No pending deposits within the 30-minute window.")
        return

    log.info(f"Found {len(to_check)} rentals needing deposit check.")

    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")
    if not email or not password:
        log.error("MPOWR credentials missing.")
        return

    headless = os.getenv("CREATOR_HEADLESS", "true").lower() == "true"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 1024})
        page = context.new_page()

        try:
            login_to_mpowr(page, email, password)

            for r in to_check:
                tw_conf = r.get("tw_confirmation")
                mpwr_id = r.get("mpwr_number")
                qty = r.get("vehicle_qty") or 1
                if isinstance(qty, str):
                    try: qty = int(qty)
                    except: qty = 1
                qty = max(1, qty)
                
                if not mpwr_id or str(mpwr_id).strip().upper() == "UNKNOWN":
                    log.warning(f"[{tw_conf}] Invalid or UNKNOWN MPOWR ID. Skipping deposit check.")
                    continue

                required_auth = float(qty * 3000)
                
                order_url = f"https://mpwr-hq.poladv.com/orders/{mpwr_id}"
                log.info(f"[{tw_conf}] Checking deposit at {order_url}")
                page.goto(order_url, timeout=30000)
                
                try:
                    page.wait_for_selector('h1:has-text("Reservation Details")', state='attached', timeout=15000)
                    time.sleep(2) # wait for data load
                except:
                    log.warning(f"[{tw_conf}] Failed to load reservation page.")
                    continue

                # Sum payment authorizations
                total_auth = 0.0
                auth_blocks = page.locator('text="Payment Authorizations"').locator("xpath=..")
                # Look for dollar amounts inside this block
                if auth_blocks.count() > 0:
                    text_content = auth_blocks.first.inner_text()
                    # Find all e.g. $3,000 or $3,000.00
                    amounts = re.findall(r'\$\s*([\d,]+\.?\d*)', text_content)
                    for a in amounts:
                        val = float(a.replace(',', ''))
                        total_auth += val

                log.info(f"[{tw_conf}] Found ${total_auth:.2f} in authorizations. Required: ${required_auth:.2f}")

                if total_auth >= required_auth:
                    # Update DB to Paid
                    try:
                        supabase.table("reservations").update({"deposit_status": "Collected"}).eq("tw_confirmation", tw_conf).execute()
                        log.info(f"[{tw_conf}] Deposit marked as Paid in Supabase.")
                    except Exception as e:
                        log.error(f"[{tw_conf}] Failed to update DB: {e}")
                else:
                    # Not paid. Check if "On Ride"
                    # MPOWR status pill
                    try:
                        status_pill = page.locator('span.inline-flex.rounded').first
                        if status_pill.count() > 0:
                            status_text = status_pill.inner_text().strip().lower()
                            if "on ride" in status_text:
                                if tw_conf not in _alerted_deposits:
                                    log.warning(f"[{tw_conf}] URGENT: Status is On Ride but deposit not paid!")
                                    slack.send_deposit_alert(tw_conf, mpwr_id, qty, required_auth)
                                    _alerted_deposits.add(tw_conf)
                                else:
                                    log.warning(f"[{tw_conf}] Status is On Ride without deposit, but alert already sent. Suppressing.")
                    except Exception as e:
                        log.warning(f"[{tw_conf}] Failed to check status pill: {e}")

        except Exception as e:
            log.error(f"Error during deposit checking loop: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    check_upcoming_deposits()
