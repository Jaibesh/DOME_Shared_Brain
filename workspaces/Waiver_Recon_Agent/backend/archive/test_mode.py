import os
import sys
import re
from dotenv import load_dotenv
from mpowr_browser import MpowrBrowser

MPOWR_BASE = "https://mpwr-hq.poladv.com"

def parse_name_and_count(raw_str):
    match = re.match(r"(.*?)\s*-\s*(\d+)", raw_str)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return raw_str.strip(), 1

def run_test(mpwr_number):
    load_dotenv()
    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")
    
    if not email or not password:
        print("Missing MPOWR_EMAIL or MPOWR_PASSWORD")
        return
        
    print(f"Testing scraper for MPWR Number: {mpwr_number}".encode('utf-8').decode('cp1252', 'ignore'))
    browser = MpowrBrowser(email, password, headless=True)
    page = browser.start()
    
    try:
        order_url = f"{MPOWR_BASE}/orders/{mpwr_number}"
        page.goto(order_url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Look for rider rows by finding the rowheader first
        rowheaders = page.locator('span[role="rowheader"], a[role="rowheader"]')
        count = rowheaders.count()
        
        print("\n--- NEW SELECTOR SCRAPING RESULTS ---")
        print(f"Found {count} rowheaders.")
        
        results = []
        for j in range(count):
            header = rowheaders.nth(j)
            name = header.inner_text().strip()
            
            # Find the parent row
            row = header.locator("xpath=ancestor::div[@role='row']")
            if row.count() > 0:
                row = row.first
                text_content = row.inner_text().encode('ascii', 'ignore').decode('ascii')
                html_content = row.inner_html()
                
                print(f"\nRider {j+1}: {name}")
                print(f"  ROW TEXT: {repr(text_content[:100])}...")
                
                if "Completed Waiver" in text_content or "Missing Waiver" in text_content:
                    import re
                    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text_content)
                    email_addr = email_match.group(0) if email_match else ""
                    
                    if email_addr.lower().startswith("polaris+") and email_addr.lower().endswith("@epic4x4adventures.com"):
                        print(f"  -> SKIPPED: This is an automated Alias placeholder email ({email_addr})")
                        continue
                    
                    is_child = "child" in html_content.lower() or "minor" in html_content.lower()
                    status = "Completed Waiver" if "Completed Waiver" in text_content else "Missing Waiver"
                    
                    if is_child:
                        name += " MINOR"
                        
                    results.append((name, status, is_child))
                    print(f"  -> PARSED: Name='{name}', Status='{status}', Minor='{is_child}'")
            else:
                print(f"\nRider {j+1}: {name} -> Could not find parent role=row")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_test(sys.argv[1])
    else:
        run_test("CO-PA3-578")
