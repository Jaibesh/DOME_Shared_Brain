import re
import time
from datetime import datetime
import pytz

from mpowr_browser import MpowrBrowser, MpowrLoginError
from waiver_link_storage import get_supabase

MDT = pytz.timezone("America/Denver")
MPOWR_BASE = "https://mpwr-hq.poladv.com"

def parse_name_and_count(raw_str):
    """
    Extracts the name and expected waiver count, e.g. "Jean-Daniel Sabourin - 4"
    Returns ("Jean-Daniel Sabourin", 4)
    """
    match = re.match(r"(.*?)\s*-\s*(\d+)", raw_str)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return raw_str.strip(), 1

def run_mpowr_scraper(email: str, password: str):
    """
    Connects to Supabase to find all upcoming reservations with an MPWR number.
    Logs into MPOWR, navigates to each reservation, extracts the riders, 
    counts completed Polaris waivers, and updates Supabase.
    """
    supabase = get_supabase()
    today_iso = datetime.now(MDT).date().isoformat()
    
    # 1. Fetch upcoming reservations with an MPWR number
    try:
        res = supabase.table("reservations") \
            .select("tw_confirmation, mpwr_number, polaris_complete, polaris_expected") \
            .gte("activity_date", today_iso) \
            .neq("mpwr_number", "") \
            .execute()
            
        all_reservations = res.data or []
    except Exception as e:
        print(f"[MPOWR Scraper] Failed to fetch reservations from Supabase: {e}")
        return
        
    # Filter out reservations that already have all waivers completed or don't need scraping
    reservations = []
    for r in all_reservations:
        mpwr_number = r.get("mpwr_number") or ""
        if mpwr_number.upper() in ("", "UNKNOWN", "NOT_REQUIRED", "0", "0.0"):
            continue
            
        pol_complete = r.get("polaris_complete") or 0
        pol_expected = r.get("polaris_expected") or 0
        
        if pol_expected > 0 and pol_complete >= pol_expected:
            # Skip: all waivers are already signed!
            continue
            
        reservations.append(r)

    if not reservations:
        print("[MPOWR Scraper] No upcoming MPWR reservations require scraping.")
        return
        
    print(f"[MPOWR Scraper] Found {len(reservations)} upcoming reservations to scrape.")

    # 2. Log into MPOWR
    browser = MpowrBrowser(email, password, headless=True)
    try:
        page = browser.start()
    except MpowrLoginError as e:
        print(f"[MPOWR Scraper] {e}")
        browser.close()  # Prevent Playwright zombie on login failure
        return

    # Tracking metrics for Slack
    reservations_checked = 0
    total_waivers_found = 0
    new_waivers_found = 0
    errors = []

    # 3. Scrape each reservation
    try:
        for i, r in enumerate(reservations):
            tw_conf = r.get('tw_confirmation')
            mpwr_number = r.get('mpwr_number')
            previous_pol_complete = r.get('polaris_complete') or 0

            # Clean mpwr_number if it's a full URL
            if mpwr_number.startswith("http"):
                mpwr_number = mpwr_number.rstrip("/").split("/")[-1]
                
            if not mpwr_number or mpwr_number.upper() == "UNKNOWN":
                print(f"[{i+1}/{len(reservations)}] Skipping UNKNOWN or missing MPWR ID for {tw_conf}.")
                continue
                
            print(f"[{i+1}/{len(reservations)}] Scraping {mpwr_number} (TW: {tw_conf})...")
            
            order_url = f"{MPOWR_BASE}/orders/{mpwr_number}"
            try:
                page.goto(order_url, timeout=30000, wait_until="domcontentloaded")
                
                # Ensure the page has actually loaded before trying to find riders
                # This prevents network timeouts from silently setting polaris_complete to 0
                page.wait_for_selector("text=Rider Actions, text=Canceled, text=Cancelled", state="attached", timeout=15000)
                
                # Dynamically wait for the riders list to render (up to 4 seconds)
                try:
                    page.wait_for_selector('span[role="rowheader"], a[role="rowheader"]', timeout=4000)
                except Exception:
                    pass # If it times out now, we know the page loaded but the list is genuinely empty
                
                # Look for rider rows explicitly by rowheader to avoid matching global nav or page titles
                rowheaders = page.locator('span[role="rowheader"], a[role="rowheader"]')
                count = rowheaders.count()
                
                polaris_complete_count = 0
                polaris_names = []
                
                for j in range(count):
                    header = rowheaders.nth(j)
                    name = header.inner_text().strip()
                    
                    # Check for alias
                    # Epic Webhook rule: Flag alias emails so front desk deletes them
                    # Since we are no longer regex-ing the whole row by default, we grab the parent row text
                    row = header.locator("xpath=ancestor::div[@role='row']").first
                    if row.count() > 0:
                        text_content = row.inner_text()
                        html_content = row.inner_html()
                        
                        if "Completed Waiver" in text_content or "Missing Waiver" in text_content:
                            # Find emails
                            email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text_content)
                            email_addr = email_match.group(0) if email_match else ""
                            
                            if email_addr.lower().startswith("polaris+") and email_addr.lower().endswith("@epic4x4adventures.com"):
                                # This is an automated placeholder from our webhook orchestrator. Skip completely!
                                continue
                            
                            # Only check for actual minor keywords, ignore standard user SVGs
                            is_child = "child" in html_content.lower() or "minor" in html_content.lower()
                            if is_child:
                                name += " ⚠️MINOR"
                            
                            if "Completed Waiver" in text_content:
                                polaris_complete_count += 1
                                polaris_names.append(name)
                
                # Update metrics
                reservations_checked += 1
                total_waivers_found += polaris_complete_count
                if polaris_complete_count > previous_pol_complete:
                    new_waivers_found += (polaris_complete_count - previous_pol_complete)

                print(f"   -> Found {polaris_complete_count} signed waivers. Names: {polaris_names}")

                # Waiver Recon Rule: "Only Increase" logic
                # Prevent MPOWR UI glitches from dropping the waiver count back down to 0
                if polaris_complete_count >= previous_pol_complete:
                    # Update Supabase
                    updates = {
                        "polaris_complete": polaris_complete_count,
                        "polaris_names": polaris_names,
                        "last_updated": datetime.now(MDT).isoformat()
                    }
                    supabase.table("reservations").update(updates).eq("tw_confirmation", tw_conf).execute()
                else:
                    print(f"   -> ⚠️ WARNING: Scraped count ({polaris_complete_count}) is lower than previous count ({previous_pol_complete}). Skipping database update to prevent data loss.")
                
            except Exception as e:
                err_msg = f"{mpwr_number} (TW: {tw_conf}): {str(e)[:100]}"
                errors.append(err_msg)
                print(f"   -> ❌ Failed to scrape {mpwr_number}: {e}")
                
            # Small jitter to avoid rate limits
            time.sleep(1)

    finally:
        browser.close()
    
    # Send Slack Summary
    from slack_notifier import SlackNotifier
    slack = SlackNotifier()
    slack.send_scraper_summary(
        reservations_checked=reservations_checked,
        total_waivers_found=total_waivers_found,
        new_waivers_found=new_waivers_found,
        errors=errors
    )
    
    print("[MPOWR Scraper] Scraping complete!")

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    run_mpowr_scraper(os.getenv("MPOWR_EMAIL"), os.getenv("MPOWR_PASSWORD"))
