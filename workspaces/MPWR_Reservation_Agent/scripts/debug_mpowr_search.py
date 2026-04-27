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
        page.wait_for_selector("input[placeholder*='Search']", timeout=10000)
        
        # Clear search
        page.fill("input[placeholder*='Search']", "")
        time.sleep(1)
        
        name = "Craig Krueger"
        print(f"Searching for: '{name}'")
        
        # Click the input first
        page.click("input[placeholder*='Search']")
        page.click("input[placeholder*='Search']")
        page.keyboard.type("Craig Krueger", delay=100)
        page.keyboard.press("Enter")
        time.sleep(3)
        
        rows = page.locator("div[role='row']").all()
        print(f"Found {len(rows)} rows for name search.")
        
        expected_date = "April 26"
        for i, row in enumerate(rows):
            text = row.inner_text()
            print(f"--- ROW {i} TEXT ---")
            print(repr(text))
            print(f"Contains '{expected_date}'?: {expected_date in text}")
            
        print("Searching by confirmation number CO-BGV-W85...")
        page.fill("input[placeholder*='Search']", "")
        time.sleep(1)
        page.click("input[placeholder*='Search']")
        page.keyboard.type("CO-BGV-W85", delay=100)
        time.sleep(3)
        rows = page.locator("div[role='row']").all()
        print(f"Found {len(rows)} rows for ID search.")
            
        browser.close()

if __name__ == "__main__":
    main()
