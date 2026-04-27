import os
import sys

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
        page.wait_for_selector("main", timeout=15000)
        
        with open("orders_dom.html", "w", encoding="utf-8") as f:
            f.write(page.content())
            
        browser.close()
        print("DOM dumped to orders_dom.html")

if __name__ == "__main__":
    main()
