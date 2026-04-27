"""
recover_mpwr_ids.py — MPOWR ID Recovery Agent

Searches MPOWR by guest name to recover existing but unlinked MPOWR IDs for 
reservations in Supabase that have a NULL mpwr_number.
"""

import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Force UTF-8 output on Windows terminals
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from supabase import create_client

# Load environment
AGENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(AGENT_ROOT, ".env"))
sys.path.append(AGENT_ROOT)

from mpowr_login import login_to_mpowr

def normalize_date_for_mpowr(date_str: str) -> str:
    """Convert YYYY-MM-DD or MM/DD/YYYY to MPOWR format (e.g. 'April 26')"""
    try:
        if " " in date_str:
            date_str = date_str.split(" ")[0]
            
        if "-" in date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            dt = datetime.strptime(date_str, "%m/%d/%Y")
        return dt.strftime("%B ") + str(dt.day)
    except Exception:
        return date_str

def should_skip(row):
    """Filter out test data and TripAdvisor/Slingshot/Pro XPerience"""
    name = row.get("guest_name", "").lower()
    activity = row.get("activity_name", "").lower()
    
    if "jennifer johnson" in name or "test test" in name:
        return True
        
    skip_keywords = ["tripadvisor", "slingshot", "pro xperience", "private ride along", "discovery"]
    for keyword in skip_keywords:
        if keyword in activity:
            if activity == "moab discovery tour":
                continue # Do not skip
            return True
            
    if "tripadvisor" in activity:
        return True
        
    return False

def get_missing_reservations(supabase) -> list:
    print("[DB] Fetching reservations with missing MPOWR IDs...")
    resp = supabase.table("reservations").select(
        "tw_confirmation, guest_name, activity_name, activity_date"
    ).is_("mpwr_number", "null").execute()
    
    rows = resp.data or []
    filtered = [r for r in rows if not should_skip(r)]
    print(f"[DB] Found {len(filtered)} actionable reservations missing IDs.")
    return filtered

def search_mpowr(page, name: str, expected_date: str) -> tuple[str | None, str]:
    """
    Search MPOWR for a guest.
    Returns: (mpwr_id, status_message)
    """
    try:
        # Navigate to orders
        page.goto("https://mpwr-hq.poladv.com/orders")
        page.wait_for_selector("input[placeholder*='Search']", timeout=10000)
        
        page.click("input[placeholder*='Search']")
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        time.sleep(1)
        
        # Search for name
        print(f"  [Search] Looking for: '{name}'")
        page.click("input[placeholder*='Search']")
        page.keyboard.type(name, delay=100)
        page.press("input[placeholder*='Search']", "Enter")
        
        time.sleep(2) # Wait for network
        
        # Check if it's the "No data available" row or get results
        rows = page.locator("div[role='row']").all()
        if not rows:
            return None, "Not Found (No results)"
            
        if len(rows) == 1:
            text = rows[0].inner_text().lower()
            if "no data" in text or "no records" in text or "no entries" in text or "no result" in text:
                return None, "Not Found (No records)"
        
        # We have results. Filter by date.
        matched_ids = []
        
        import re
        for row in rows:
            text = row.inner_text()
            if expected_date in text:
                # Extract CO-XXX-XXX using regex from the text
                match = re.search(r'(CO-[A-Z0-9]{3}-[A-Z0-9]{3})', text)
                if match:
                    mpwr_id = match.group(1)
                    matched_ids.append(mpwr_id)
        
        if not matched_ids:
            return None, "Not Found (Date mismatch)"
            
        # Deduplicate
        matched_ids = list(set(matched_ids))
        
        if len(matched_ids) == 1:
            return matched_ids[0], "Recovered"
        else:
            return None, f"Ambiguous ({len(matched_ids)} matches found for date)"
            
    except Exception as e:
        return None, f"Error: {e}"

def main():
    parser = argparse.ArgumentParser(description="Recover MPOWR IDs")
    parser.add_argument("--live", action="store_true", help="Save found IDs to Supabase")
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")
    
    if not all([url, key, email, password]):
        print("Missing required environment variables.")
        return

    supabase = create_client(url, key)
    missing = get_missing_reservations(supabase)
    
    if not missing:
        print("Nothing to do.")
        return
        
    print(f"Starting MPOWR Recovery Agent... Live mode: {args.live}")
    
    stats = {"Recovered": 0, "Not Found": 0, "Ambiguous": 0, "Error": 0}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            login_to_mpowr(page, email, password)
            
            for i, res in enumerate(missing, 1):
                name = res["guest_name"]
                tw = res["tw_confirmation"]
                date = normalize_date_for_mpowr(res["activity_date"])
                
                print(f"[{i}/{len(missing)}] {tw} - {name} ({date})")
                
                mpwr_id, status = search_mpowr(page, name, date)
                
                if mpwr_id:
                    print(f"  ✅ FOUND: {mpwr_id}")
                    stats["Recovered"] += 1
                    
                    if args.live:
                        try:
                            supabase.table("reservations").update({
                                "mpwr_number": mpwr_id,
                                "last_updated": datetime.utcnow().isoformat()
                            }).eq("tw_confirmation", tw).execute()
                            print("  💾 Saved to database.")
                        except Exception as e:
                            print(f"  ❌ DB Error: {e}")
                else:
                    if "Ambiguous" in status:
                        print(f"  ⚠️ {status}")
                        stats["Ambiguous"] += 1
                    elif "Error" in status:
                        print(f"  ❌ {status}")
                        stats["Error"] += 1
                    else:
                        print(f"  🗑️ {status}")
                        stats["Not Found"] += 1
                        
                time.sleep(1) # Be nice to MPOWR
                
        except Exception as e:
            print(f"Fatal error: {e}")
        finally:
            browser.close()
            
    print("\n" + "="*40)
    print("RECOVERY SUMMARY")
    print("="*40)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("="*40)

if __name__ == "__main__":
    main()
