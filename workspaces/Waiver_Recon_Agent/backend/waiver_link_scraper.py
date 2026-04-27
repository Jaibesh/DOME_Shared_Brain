"""
waiver_link_scraper.py — MPOWR Waiver QR Code & Link Extractor

Navigates to each MPOWR reservation page, clicks:
    Rider Actions → Show Waiver QR Code
and extracts:
    1. The unique join URL (e.g., https://adventures.polaris.com/join/RES-42V-EK7)
    2. The QR code image as PNG bytes

Standalone module — zero coupling to the MPWR Reservation Agent.
Uses a dedicated MPOWR login to avoid session conflicts.
"""

import os
import re
import time
import glob
import random
import atexit
from datetime import datetime, timedelta

import pytz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

MDT = pytz.timezone("America/Denver")
MPOWR_BASE = "https://mpwr-hq.poladv.com"


def _extract_mpwr_id(raw_value: str) -> str:
    """
    Extract the bare MPWR confirmation ID from a value that may be:
      - A bare ID like "CO-MAR-RD8"
      - A full join URL like "https://adventures.polaris.com/join/CO-MAR-RD8"
      - An MPWR orders URL like "https://mpwr-hq.poladv.com/orders/CO-MAR-RD8"
    """
    raw = raw_value.strip()
    if not raw:
        return ""
    # If it's a URL, extract the last path segment as the ID
    if raw.startswith("http"):
        # Strip trailing slashes and get last segment
        cleaned = raw.rstrip("/")
        return cleaned.split("/")[-1]
    return raw

# The generic waiver link that we're replacing
GENERIC_WAIVER_LINK = "https://adventures.polaris.com/our-outfitters/epic-4x4-adventures-O-DZ6-478/waiver/rider-info"

# Safety: stop batch if N consecutive failures (prevents infinite login loops)
MAX_CONSECUTIVE_FAILURES = 5


class WaiverLinkScraper:
    """Playwright-based MPOWR waiver QR code and join URL extractor."""

    def __init__(self, email: str, password: str, headless: bool = True):
        self.email = email
        self.password = password
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._is_logged_in = False
        self._screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        os.makedirs(self._screenshots_dir, exist_ok=True)

        # Register cleanup handler
        atexit.register(self.stop)

    def start(self):
        """Launch the browser and log into MPOWR."""
        if self._browser:
            return  # Already running

        # Clean up old screenshots (older than 7 days) to prevent disk growth
        self._cleanup_old_screenshots()

        print(f"[WaiverScraper] Launching Chromium (headless={self.headless})...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900}
        )
        self._page = self._context.new_page()
        self._login()

    def _login(self):
        """Drive the MPOWR SSO login flow."""
        page = self._page
        print(f"[WaiverScraper] Logging into MPOWR as {self.email}...")

        for attempt in range(1, 4):
            try:
                page.goto(f"{MPOWR_BASE}/orders", timeout=20000)

                # Handle pre-SSO gateway button
                try:
                    page.wait_for_selector("button.bg-polaris-600", timeout=5000)
                    page.click("button.bg-polaris-600")
                    print("[WaiverScraper] Pre-SSO gateway clicked.")
                except Exception:
                    pass

                # Fill credentials
                page.wait_for_selector("#username", timeout=10000)
                page.fill("#username", self.email)
                page.fill("#password", self.password)

                # Submit
                page.click("button.js-branded-button")
                page.wait_for_url("**/orders**", timeout=15000)

                self._is_logged_in = True
                print("[WaiverScraper] Login successful.")
                return

            except Exception as e:
                print(f"[WaiverScraper] Login attempt {attempt}/3 failed: {e}")
                if attempt < 3:
                    time.sleep(3)

        raise RuntimeError(f"MPOWR login failed after 3 attempts for {self.email}")

    def _ensure_logged_in(self):
        """Re-login if session has expired."""
        if not self._is_logged_in or not self._page:
            self.start()
            return

        try:
            # Check 1: Are we still on an MPOWR page?
            current_url = self._page.url
            if "poladv.com" not in current_url:
                print("[WaiverScraper] Session expired (left MPOWR domain). Re-logging in...")
                self._login()
                return

            # Check 2: Did SSO redirect us to the login page?
            if self._page.locator("#username").count() > 0:
                print("[WaiverScraper] Session expired (SSO login detected). Re-logging in...")
                self._login()
                return
        except Exception:
            self._login()

    def scrape_waiver_link(self, mpwr_id: str) -> dict:
        """
        Scrape the unique waiver QR code and join URL for a single MPWR reservation.

        Args:
            mpwr_id: The MPWR confirmation ID (e.g., "CO-M2G-Y9R")

        Returns:
            {
                "mpwr_id": str,
                "waiver_link": str or None,   # e.g. "https://adventures.polaris.com/join/RES-42V-EK7"
                "qr_image_bytes": bytes or None,
                "error": str or None,
            }
        """
        self._ensure_logged_in()
        page = self._page
        result = {
            "mpwr_id": mpwr_id,
            "waiver_link": None,
            "qr_image_bytes": None,
            "error": None,
        }

        try:
            # 1. Navigate to the reservation page
            order_url = f"{MPOWR_BASE}/orders/{mpwr_id}"
            print(f"  [Scrape] Navigating to {order_url}...")
            page.goto(order_url, timeout=30000, wait_until="domcontentloaded")

            # 2. Wait for page load and check for cancellation
            try:
                # Wait for either the top-level Actions button or Canceled badge to indicate page loaded
                page.wait_for_selector("button:has-text('Actions'), text=Canceled, text=Cancelled", state="attached", timeout=15000)
            except PlaywrightTimeout:
                pass  # Fall through to specific checks

            # Check for Canceled badge
            canceled_badge = page.locator("span, div").filter(has_text=re.compile(r"^Canceled$|^Cancelled$", re.IGNORECASE))
            is_canceled = canceled_badge.count() > 0

            if not is_canceled:
                # Fallback: Check $0 totals if badge is missing
                try:
                    body_text = page.inner_text("body").lower()
                    if "subtotal\n$0" in body_text and "total\n$0" in body_text:
                        is_canceled = True
                except Exception:
                    pass

            if is_canceled:
                result["error"] = "CANCELED"
                print(f"  [Scrape] Reservation {mpwr_id} is canceled. Skipping.")
                return result

            # 3. Wait for "Rider Actions" button as the page-ready signal
            #    (networkidle never resolves — MPOWR React app polls continuously)
            rider_actions_btn = page.locator("button:has-text('Rider Actions')")
            try:
                rider_actions_btn.wait_for(state="attached", timeout=10000)
            except PlaywrightTimeout:
                # Could be a cancelled/invalid reservation or page didn't load
                page_text = page.inner_text("body")[:500]
                if "not found" in page_text.lower() or "404" in page_text:
                    result["error"] = f"Reservation {mpwr_id} not found in MPOWR"
                else:
                    result["error"] = f"Rider Actions button not found on {mpwr_id}"
                self._screenshot(f"no_rider_actions_{mpwr_id}")
                return result

            rider_actions_btn.click()
            page.wait_for_timeout(800)  # Wait for dropdown animation

            # 3. Click "Show Waiver QR Code" in dropdown
            qr_option = page.locator("text=Show Waiver QR Code")
            try:
                qr_option.wait_for(state="attached", timeout=5000)
            except PlaywrightTimeout:
                page.keyboard.press("Escape")
                result["error"] = f"No 'Show Waiver QR Code' option in dropdown for {mpwr_id}"
                self._screenshot(f"no_qr_option_{mpwr_id}")
                return result

            qr_option.click()

            # 4. Wait for QR code modal to appear
            try:
                page.wait_for_selector("img[alt='Waiver QR Code']", timeout=10000)
            except PlaywrightTimeout:
                result["error"] = f"QR code modal did not appear for {mpwr_id}"
                self._screenshot(f"qr_modal_timeout_{mpwr_id}")
                return result

            page.wait_for_timeout(500)  # Let image fully render

            # 5. Extract the unique join URL
            # The URL is in a div with font-mono class inside the modal
            url_element = page.locator("div.overflow-x-auto.text-nowrap.font-mono, div.font-mono.text-sm")
            if url_element.count() > 0:
                waiver_url = url_element.first.inner_text().strip()
            else:
                # Fallback: look for any text matching the join URL pattern
                modal_text = page.locator("div:has(img[alt='Waiver QR Code'])").inner_text()
                url_match = re.search(r"https://adventures\.polaris\.com/join/[\w-]+", modal_text)
                if url_match:
                    waiver_url = url_match.group(0)
                else:
                    result["error"] = f"Could not find join URL in QR modal for {mpwr_id}"
                    self._screenshot(f"no_url_in_modal_{mpwr_id}")
                    # Still try to get the QR code image
                    waiver_url = None

            if waiver_url:
                # Validate URL format
                if re.match(r"https://adventures\.polaris\.com/join/[\w-]+", waiver_url):
                    result["waiver_link"] = waiver_url
                    print(f"  [Scrape] ✅ Found waiver link: {waiver_url}")
                else:
                    print(f"  [Scrape] ⚠️ URL doesn't match expected pattern: {waiver_url}")
                    result["waiver_link"] = waiver_url  # Save it anyway

            # 6. Capture the QR code image
            qr_img = page.locator("img[alt='Waiver QR Code']")
            if qr_img.count() > 0:
                try:
                    qr_bytes = qr_img.screenshot(type="png")
                    result["qr_image_bytes"] = qr_bytes
                    print(f"  [Scrape] ✅ Captured QR code image ({len(qr_bytes)} bytes)")
                except Exception as img_err:
                    print(f"  [Scrape] ⚠️ Failed to capture QR image: {img_err}")

            # 7. Close the modal
            self._close_modal(page)

        except PlaywrightTimeout as e:
            result["error"] = f"Timeout while scraping {mpwr_id}: {e}"
            self._screenshot(f"timeout_{mpwr_id}")
        except Exception as e:
            result["error"] = f"Error scraping {mpwr_id}: {e}"
            self._screenshot(f"error_{mpwr_id}")

        return result

    def _close_modal(self, page):
        """Close the QR code modal."""
        try:
            # Look for the close/X button specifically
            x_buttons = page.locator("button:has(svg.h-6.w-6), button[aria-label='Close'], button:has-text('×')")
            if x_buttons.count() > 0:
                x_buttons.first.click()
            else:
                # Fallback: press Escape
                page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

    def scrape_batch(self, reservations: list) -> list:
        """
        Scrape waiver links for a batch of reservations.

        Args:
            reservations: List of dicts with "tw_confirmation" and "mpwr_number" keys

        Returns:
            List of result dicts from scrape_waiver_link(), augmented with tw_confirmation
        """
        if not reservations:
            return []

        self._ensure_logged_in()
        results = []
        consecutive_failures = 0

        for i, res in enumerate(reservations):
            mpwr_id = _extract_mpwr_id(str(res.get("mpwr_number", "")))
            tw_conf = str(res.get("tw_confirmation", "")).strip()

            if not mpwr_id:
                results.append({
                    "mpwr_id": "",
                    "tw_confirmation": tw_conf,
                    "waiver_link": None,
                    "qr_image_bytes": None,
                    "error": "No mpwr_number provided",
                })
                continue

            print(f"\n[WaiverScraper] [{i+1}/{len(reservations)}] Scraping {mpwr_id} (TW: {tw_conf})...")

            result = self.scrape_waiver_link(mpwr_id)
            result["tw_confirmation"] = tw_conf

            if result.get("error"):
                consecutive_failures += 1
                print(f"  [Scrape] ❌ Failed: {result['error']}")

                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\n[WaiverScraper] ⛔ {MAX_CONSECUTIVE_FAILURES} consecutive failures. "
                          f"Aborting batch to prevent cascading errors.")
                    # Append current failure first, then mark remaining as skipped
                    results.append(result)
                    for remaining in reservations[i+1:]:
                        results.append({
                            "mpwr_id": remaining.get("mpwr_number", ""),
                            "tw_confirmation": remaining.get("tw_confirmation", ""),
                            "waiver_link": None,
                            "qr_image_bytes": None,
                            "error": "Batch aborted due to consecutive failures",
                        })
                    break
            else:
                consecutive_failures = 0

            results.append(result)

            # Random jitter between requests (2-4 seconds)
            if i < len(reservations) - 1:
                jitter = random.uniform(2.0, 4.0)
                time.sleep(jitter)

        return results

    def _screenshot(self, label: str):
        """Capture a diagnostic screenshot."""
        try:
            # Sanitize label for Windows filenames (remove : / \ etc.)
            safe_label = re.sub(r'[<>:"/\\|?*]', '_', label)
            ts = datetime.now(MDT).strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._screenshots_dir, f"waiver_scraper_{safe_label}_{ts}.png")
            self._page.screenshot(path=path, full_page=True)
            print(f"  [Screenshot] Saved: {path}")
        except Exception as e:
            print(f"  [Screenshot] Failed to capture: {e}")

    def _cleanup_old_screenshots(self, max_age_days: int = 7):
        """Remove screenshots older than max_age_days to prevent disk growth."""
        try:
            cutoff = (datetime.now(MDT) - timedelta(days=max_age_days)).timestamp()
            pattern = os.path.join(self._screenshots_dir, "waiver_scraper_*.png")
            removed = 0
            for f in glob.glob(pattern):
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
                    removed += 1
            if removed:
                print(f"[WaiverScraper] Cleaned up {removed} screenshots older than {max_age_days} days.")
        except Exception as e:
            print(f"[WaiverScraper] Screenshot cleanup failed (non-fatal): {e}")

    def stop(self):
        """Gracefully close the browser."""
        try:
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            self._is_logged_in = False
            self._page = None
            self._context = None
            print("[WaiverScraper] Browser closed.")
        except Exception as e:
            print(f"[WaiverScraper] Error during cleanup: {e}")

    def __del__(self):
        self.stop()
