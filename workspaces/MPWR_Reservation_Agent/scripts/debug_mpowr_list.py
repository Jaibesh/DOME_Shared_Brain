import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

AGENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(AGENT_ROOT)
from mpowr_login import login_to_mpowr

load_dotenv(os.path.join(AGENT_ROOT, ".env"))

def main():
    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        login_to_mpowr(page, email, password)
        page.goto("https://mpwr-hq.poladv.com/orders")
        page.wait_for_selector("table tbody tr", timeout=15000)
        time.sleep(2) # Let data load fully
        
        # Look for the 'Upcoming' tab and click it if available
        try:
            upcoming_tab = page.locator("text=Upcoming").first
            if upcoming_tab:
                upcoming_tab.click()
                time.sleep(2)
        except Exception as e:
            print("Could not click Upcoming tab", e)
            
        print("--- PAGE 1 RESULTS ---")
        rows = page.locator("table tbody tr").all()
        for row in rows:
            text = row.inner_text().replace('\n', ' | ')
            link = row.locator("a[href*='/orders/CO-']").first
            mpwr_id = "UNKNOWN"
            if link.count() > 0:
                mpwr_id = link.get_attribute("href").split("/")[-1]
            print(f"{mpwr_id}: {text[:100]}...")
            
        browser.close()

if __name__ == "__main__":
    main()
