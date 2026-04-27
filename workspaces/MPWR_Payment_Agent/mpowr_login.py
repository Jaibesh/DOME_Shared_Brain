"""
mpowr_login.py — Shared MPOWR Authentication Module

Extracts the login flow used by the mpowr payment bot into a single, maintainable module.
"""

import time
from playwright.sync_api import Page

class MpowrLoginError(Exception):
    """Raised when MPOWR login fails after all retries."""
    pass

def login_to_mpowr(page: Page, email: str, password: str, max_retries: int = 2) -> bool:
    """
    Drives the MPOWR login flow on an existing Playwright page.

    Args:
        page: An active Playwright page object
        email: MPOWR login email
        password: MPOWR login password
        max_retries: Number of login attempts before raising MpowrLoginError

    Returns:
        True on successful login
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[MPOWR Login] Attempt {attempt}/{max_retries}...")
            page.goto("https://mpwr-hq.poladv.com/orders", timeout=20000)

            try:
                page.wait_for_selector('button.bg-polaris-600', timeout=5000)
                page.click('button.bg-polaris-600')
                print("[MPOWR Login] Pre-SSO gateway clicked.")
            except Exception:
                pass

            page.wait_for_selector('#username', timeout=10000)
            page.fill('#username', email)
            page.fill('#password', password)
            print("[MPOWR Login] Credentials entered.")

            page.click('button.js-branded-button')

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
