"""
mpowr_browser.py — Centralized MPOWR Login Framework

Provides a robust, shared Playwright login flow for MPOWR that successfully 
handles the Pre-SSO Gateway button and session persistence.
Used by both the Waiver Scraper and the Waiver Link Scraper.
"""

import time
from playwright.sync_api import sync_playwright, Page, Browser, Playwright, BrowserContext

MPOWR_BASE = "https://mpwr-hq.poladv.com"

class MpowrLoginError(Exception):
    pass

class MpowrBrowser:
    def __init__(self, email: str, password: str, headless: bool = True):
        self.email = email
        self.password = password
        self.headless = headless
        
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def start(self) -> Page:
        """Starts the browser and logs into MPOWR, returning the active Page."""
        print(f"[MPOWR] Launching Chromium (headless={self.headless})...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.page = self.context.new_page()

        print(f"[MPOWR] Logging into MPOWR as {self.email}...")

        for attempt in range(1, 4):
            try:
                self.page.goto(f"{MPOWR_BASE}/orders", timeout=20000)

                # Handle pre-SSO gateway button
                try:
                    self.page.wait_for_selector("button.bg-polaris-600", timeout=5000)
                    self.page.click("button.bg-polaris-600")
                    print("[MPOWR] Pre-SSO gateway clicked.")
                except Exception:
                    pass

                # Fill credentials
                self.page.wait_for_selector("#username", timeout=10000)
                self.page.fill("#username", self.email)
                self.page.fill("#password", self.password)

                # Submit
                self.page.click("button.js-branded-button")
                self.page.wait_for_url("**/orders**", timeout=15000)

                print("[MPOWR] Login successful.")
                return self.page

            except Exception as e:
                print(f"[MPOWR] Login attempt {attempt}/3 failed: {e}")
                if attempt < 3:
                    time.sleep(3)

        self.close()
        raise MpowrLoginError(f"MPOWR login failed after 3 attempts for {self.email}")

    def close(self):
        """Gracefully closes the browser session."""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            print("[MPOWR] Browser closed.")
        except Exception as e:
            print(f"[MPOWR] Error closing browser: {e}")
