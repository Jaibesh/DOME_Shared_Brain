"""
mpwr_waiver_sync.py — Fast MPOWR Waiver Reconciliation Daemon

Runs every 30 seconds.
1. Queries Supabase for today's reservations where Polaris waivers are incomplete.
2. If any exist, uses a persistent Playwright browser to scrape their specific MPWR pages.
3. Updates Supabase directly if new waivers are found.

Usage:
Requires dedicated login credentials in .env to avoid rate-limiting the main creator bot.
  MPOWR_WAIVER_EMAIL=...
  MPOWR_WAIVER_PASSWORD=...
"""

import os
import time
import re
from datetime import datetime
import pytz
from dotenv import load_dotenv

from playwright.sync_api import sync_playwright, TimeoutError
from supabase_client import get_supabase

# Add Waiver_Recon_Agent/backend to path so we can use its mpowr_login logic if needed
# Actually, the login logic is simple enough to just include here to keep it standalone.

load_dotenv()

MDT = pytz.timezone("America/Denver")
MPOWR_URL = "https://mpwr-hq.poladv.com"

# The dedicated login for the waiver scraper
EMAIL = os.getenv("MPOWR_WAIVER_EMAIL", "")
PASSWORD = os.getenv("MPOWR_WAIVER_PASSWORD", "")


def get_pending_reservations(supabase):
    """Fetch today's reservations that are missing Polaris waivers."""
    today_iso = datetime.now(MDT).date().isoformat()
    
    # We need reservations for today where polaris_expected > polaris_complete
    # And we must have an mpwr_number to scrape
    res = supabase.table("reservations") \
        .select("tw_confirmation, mpwr_number, polaris_expected, polaris_complete, polaris_names") \
        .eq("activity_date", today_iso) \
        .neq("mpwr_number", "") \
        .execute()
        
    pending = []
    for r in (res.data or []):
        expected = int(r.get("polaris_expected") or 0)
        completed = int(r.get("polaris_complete") or 0)
        
        # Also include cases where expected isn't set yet but we have an mpwr_number
        if expected == 0 or completed < expected:
            pending.append(r)
            
    return pending


def parse_rider_name(raw_text):
    """Extract name from MPOWR rider text block."""
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    raw_name = lines[0] if lines else "Unknown"
    # Remove the "- 4" count suffix if present
    match = re.match(r"(.*?)\s*-\s*(\d+)", raw_name)
    if match:
        return match.group(1).strip()
    return raw_name.strip()


def run_sync_loop():
    if not EMAIL or not PASSWORD:
        print("[Error] MPOWR_WAIVER_EMAIL and MPOWR_WAIVER_PASSWORD must be set in .env")
        return

    supabase = get_supabase()
    
    print("🚀 Starting Fast MPOWR Waiver Sync Daemon...")
    print(f"Using dedicated account: {EMAIL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        is_logged_in = False
        
        while True:
            try:
                pending = get_pending_reservations(supabase)
                now_str = datetime.now(MDT).strftime("%I:%M:%S %p")
                
                if not pending:
                    print(f"[{now_str}] All caught up. No pending waivers for today. Sleeping 30s...")
                    time.sleep(30)
                    continue
                    
                print(f"[{now_str}] Found {len(pending)} reservations missing waivers. Checking MPOWR...")
                
                # Ensure we're logged in
                if not is_logged_in:
                    print("Logging into MPOWR...")
                    page.goto(f"{MPOWR_URL}/login")
                    page.fill("input[type='email']", EMAIL)
                    page.fill("input[type='password']", PASSWORD)
                    page.click("button[type='submit']")
                    page.wait_for_url("**/orders**", timeout=15000)
                    is_logged_in = True
                    print("Login successful.")

                for res in pending:
                    tw_conf = res["tw_confirmation"]
                    mpwr_num = res["mpwr_number"]
                    current_complete = int(res.get("polaris_complete") or 0)
                    current_names = res.get("polaris_names") or []
                    
                    # Go directly to the reservation page
                    order_url = f"{MPOWR_URL}/orders/{mpwr_num}"
                    try:
                        page.goto(order_url)
                        page.wait_for_load_state("domcontentloaded")
                        # Wait a moment for rider data to populate via React
                        page.wait_for_timeout(2000)
                        
                        # Find riders
                        rider_elements = page.locator("div:has-text('Riders')").locator("xpath=..").locator("div.flex, div[class*='row']")
                        count = rider_elements.count()
                        
                        completed_names = []
                        for i in range(count):
                            text = rider_elements.nth(i).inner_text()
                            if "Completed Waiver" in text:
                                name = parse_rider_name(text)
                                completed_names.append(name)
                        
                        new_complete_count = len(completed_names)
                        
                        # If the number of completed waivers increased, update Supabase
                        if new_complete_count > current_complete:
                            print(f"  [UPDATE] {tw_conf} ({mpwr_num}): {current_complete} -> {new_complete_count} completed.")
                            
                            # Merge existing names with new names (avoid duplicates)
                            all_names = list(set(current_names + completed_names))
                            
                            supabase.table("reservations").update({
                                "polaris_complete": new_complete_count,
                                "polaris_names": all_names,
                                "last_updated": datetime.now(MDT).isoformat()
                            }).eq("tw_confirmation", tw_conf).execute()
                        else:
                            print(f"  [OK] {tw_conf}: Still at {current_complete} completed.")
                            
                    except TimeoutError:
                        print(f"  [TIMEOUT] Could not load {mpwr_num}. Skipping.")
                        continue
                        
                # Sleep before next cycle
                print("Cycle complete. Sleeping 30 seconds...")
                time.sleep(30)
                
            except Exception as e:
                print(f"[Error] Exception in sync loop: {e}")
                # If it's a session issue, we'll try to re-login next loop
                is_logged_in = False
                time.sleep(10)


if __name__ == "__main__":
    run_sync_loop()
