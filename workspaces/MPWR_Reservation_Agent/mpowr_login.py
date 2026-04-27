"""
mpowr_login.py — Shared MPOWR Authentication Module

Extracts the login flow used by both scraper.py and mpowr_creator_bot.py
into a single, maintainable module. If Polaris changes their login UI,
fix it here and both systems update automatically.
"""

import time
from playwright.sync_api import Page


class MpowrLoginError(Exception):
    """Raised when MPOWR login fails after all retries."""
    pass


def login_to_mpowr(page: Page, email: str, password: str, max_retries: int = 2) -> bool:
    """
    Drives the MPOWR login flow on an existing Playwright page.

    Flow:
    1. Navigate to https://mpwr-hq.poladv.com/orders
    2. Handle optional pre-SSO gateway button (button.bg-polaris-600)
    3. Fill #username and #password
    4. Click button.js-branded-button
    5. Wait for URL to match **/orders**

    Args:
        page: An active Playwright page object
        email: MPOWR login email
        password: MPOWR login password
        max_retries: Number of login attempts before raising MpowrLoginError

    Returns:
        True on successful login

    Raises:
        MpowrLoginError: If login fails after max_retries attempts
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[MPOWR Login] Attempt {attempt}/{max_retries}...")
            page.goto("https://mpwr-hq.poladv.com/orders", timeout=20000)

            # Handle pre-SSO gateway click (Polaris branded button)
            try:
                page.wait_for_selector('button.bg-polaris-600', timeout=5000)
                page.click('button.bg-polaris-600')
                print("[MPOWR Login] Pre-SSO gateway clicked.")
            except Exception:
                # Gateway button may not always appear
                pass

            # Fill credentials
            page.wait_for_selector('#username', timeout=10000)
            page.fill('#username', email)
            page.fill('#password', password)
            print("[MPOWR Login] Credentials entered.")

            # Submit login
            page.click('button.js-branded-button')

            # Wait for successful navigation to orders dashboard
            page.wait_for_url("**/orders**", timeout=15000)
            print("[MPOWR Login] Login successful.")
            return True

        except Exception as e:
            last_error = e
            print(f"[MPOWR Login] Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                print(f"[MPOWR Login] Retrying in 3 seconds...")
                time.sleep(3)

    raise MpowrLoginError(
        f"Login failed after {max_retries} attempts. Last error: {last_error}"
    )
