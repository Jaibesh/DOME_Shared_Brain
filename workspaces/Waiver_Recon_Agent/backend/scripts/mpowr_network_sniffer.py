import os
import sys
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def run_sniffer():
    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")
    
    if not email or not password:
        print("ERROR: MPOWR_EMAIL or MPOWR_PASSWORD is not set in .env")
        return

    print("Launching Playwright to capture network traffic...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(record_har_path="mpowr_network.har")
        page = context.new_page()

        page.goto("https://mpwr-hq.poladv.com/orders")

        print("Attempting automatic login...")
        try:
            try:
                page.wait_for_selector('button.bg-polaris-600', timeout=5000)
                page.click('button.bg-polaris-600')
            except:
                pass
                
            page.wait_for_selector('#username', timeout=10000)
            page.fill('#username', email)
            page.fill('#password', password)
            page.click('button.js-branded-button')
            page.wait_for_url("**/orders**", timeout=15000)
            print("Login successful.")
        except Exception as e:
            print("Login script issue. Please log in manually.")
            
        print("\n=======================================================")
        print("HAR RECORDER IS ACTIVE.")
        print("1. Please manually create ONE MORE TEST RESERVATION (I am so sorry for the inconvenience).")
        print("2. DO NOT CLOSE the browser when you are finished.")
        print("3. Simply reply to my chat message saying 'Done!'")
        print("=======================================================\n")
        
        # We read from stdin. The AI will send a newline to trigger the close.
        sys.stdin.readline()
        
        print("Saving HAR file specifically by closing context first...")
        context.close()
        browser.close()
        print("Browser closed. HAR file recorded to mpowr_network.har")

if __name__ == "__main__":
    run_sniffer()
