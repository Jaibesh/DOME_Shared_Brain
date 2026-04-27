"""
waiver_link_daemon.py — Standalone Waiver Link Scraper Daemon

Polls Supabase every 2 minutes for MPWR reservations that are missing their
unique waiver join link. When found, uses Playwright to scrape the link + QR code
from MPOWR and updates the database.

This process is FULLY STANDALONE — zero coupling to the MPWR Reservation Agent.
Detection is purely database-driven: it watches for reservations where
mpwr_number exists but mpwr_waiver_link is empty or generic.

Usage:
    python waiver_link_daemon.py

Requires .env:
    MPOWR_EMAIL=waiveragent@epic4x4adventures.com
    MPOWR_PASSWORD=...
    SUPABASE_URL=...
    SUPABASE_KEY=...
"""

import os
import sys
import time
import json
import signal
from datetime import datetime

import pytz
from dotenv import load_dotenv

from waiver_link_scraper import WaiverLinkScraper
from waiver_link_storage import (
    get_reservations_needing_waiver_links,
    upload_qr_code,
    update_reservation_waiver_link,
)

load_dotenv()

MDT = pytz.timezone("America/Denver")

# Configuration
POLL_INTERVAL_PEAK = 120      # 2 minutes during operating hours
POLL_INTERVAL_OFFPEAK = 900   # 15 minutes off-hours
OPERATING_HOURS = (6, 22)     # 6 AM to 10 PM MDT

# Global scraper instance (lazy-initialized to avoid starting browser at import time)
_scraper: WaiverLinkScraper | None = None
_idle_cycles = 0
MAX_IDLE_CYCLES_BEFORE_CLOSE = 5  # Close browser after 5 idle cycles (~10 min) to save resources

# Dead letter tracker: {tw_conf: {"failures": int, "last_failure": iso_timestamp}}
# Prevents permanently broken reservations from retrying every 2 minutes
_failure_tracker: dict = {}
MAX_FAILURES_BEFORE_COOLDOWN = 3
COOLDOWN_MINUTES = 60  # Skip for 1 hour after repeated failures


def _get_scraper() -> WaiverLinkScraper:
    """Lazy-initialize the scraper with credentials from .env."""
    global _scraper
    if _scraper is None:
        email = os.getenv("MPOWR_EMAIL", "")
        password = os.getenv("MPOWR_PASSWORD", "")
        headless = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"

        if not email or not password:
            raise ValueError("MPOWR_EMAIL and MPOWR_PASSWORD must be set in .env")

        _scraper = WaiverLinkScraper(
            email=email,
            password=password,
            headless=headless,
        )
    return _scraper


def _close_scraper():
    """Shut down the browser to free resources."""
    global _scraper
    if _scraper is not None:
        _scraper.stop()
        _scraper = None
        print("[Daemon] Browser closed (idle resource savings).")


def _send_slack_notification(message: str):
    """Send a Slack notification. Non-fatal if it fails."""
    try:
        import requests
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            return

        requests.post(webhook_url, json={"text": message}, timeout=10)
    except Exception as e:
        print(f"[Slack] Failed to send notification: {e}")


def run_scraper_cycle():
    """
    Main polling cycle. Queries Supabase for reservations needing waiver links,
    scrapes them, and updates the database.
    """
    global _idle_cycles

    now = datetime.now(MDT)

    print(f"\n{'='*60}")
    print(f"[{now.strftime('%I:%M:%S %p')}] Starting waiver link scan...")
    print(f"{'='*60}")

    # 1. Query for reservations needing links
    try:
        pending = get_reservations_needing_waiver_links()
    except Exception as e:
        print(f"[Daemon] Error querying Supabase: {e}")
        return

    if not pending:
        _idle_cycles += 1
        print(f"[Daemon] No reservations need waiver links. Idle cycle {_idle_cycles}/{MAX_IDLE_CYCLES_BEFORE_CLOSE}.")

        # Close browser after extended idle to save resources
        if _idle_cycles >= MAX_IDLE_CYCLES_BEFORE_CLOSE:
            _close_scraper()
            _idle_cycles = 0
        return

    # Reset idle counter — we have work to do
    _idle_cycles = 0

    print(f"[Daemon] Found {len(pending)} reservations needing waiver links.")

    # Filter out reservations in cooldown (too many consecutive failures)
    now_ts = datetime.now(MDT)
    filtered = []
    cooldown_count = 0
    for r in pending:
        tw_conf = r.get("tw_confirmation", "")
        tracker = _failure_tracker.get(tw_conf)
        if tracker and tracker["failures"] >= MAX_FAILURES_BEFORE_COOLDOWN:
            # Check if cooldown has elapsed
            last_fail = datetime.fromisoformat(tracker["last_failure"])
            minutes_since = (now_ts - last_fail).total_seconds() / 60
            if minutes_since < COOLDOWN_MINUTES:
                cooldown_count += 1
                continue  # Still in cooldown, skip
            else:
                # Cooldown elapsed, reset and retry
                _failure_tracker.pop(tw_conf, None)
        filtered.append(r)

    if cooldown_count:
        print(f"[Daemon] Skipped {cooldown_count} reservations in failure cooldown.")

    if not filtered:
        print(f"[Daemon] All pending reservations are in cooldown. Nothing to do.")
        return

    for r in filtered:
        print(f"  - {r.get('tw_confirmation')} (MPWR: {r.get('mpwr_number')}) "
              f"| {r.get('guest_name', 'Unknown')} | {r.get('activity_date', '?')}")

    # 2. Launch scraper and process batch
    try:
        scraper = _get_scraper()
        scraper.start()
    except Exception as e:
        print(f"[Daemon] Failed to start scraper: {e}")
        _send_slack_notification(f"⚠️ [WAIVER LINK SCRAPER] Failed to start browser: {e}")
        _close_scraper()
        return

    results = scraper.scrape_batch(filtered)

    # 3. Process results: upload QR codes and update database
    success_count = 0
    error_count = 0
    success_details = []

    for result in results:
        tw_conf = result.get("tw_confirmation", "")
        mpwr_id = result.get("mpwr_id", "")
        waiver_link = result.get("waiver_link")
        qr_bytes = result.get("qr_image_bytes")
        error = result.get("error")

        if error:
            if error == "CANCELED":
                # Permanently mark as CANCELED in Supabase to prevent further retries
                update_reservation_waiver_link(tw_conf, "CANCELED", None)
                print(f"  [Result] 🛑 {tw_conf} ({mpwr_id}): Marked as CANCELED in DB")
                continue

            error_count += 1
            print(f"  [Result] ❌ {tw_conf} ({mpwr_id}): {error}")
            # Track failure for dead letter cooldown
            if tw_conf:
                prev = _failure_tracker.get(tw_conf, {"failures": 0})
                _failure_tracker[tw_conf] = {
                    "failures": prev["failures"] + 1,
                    "last_failure": datetime.now(MDT).isoformat(),
                }
            continue

        if not waiver_link:
            error_count += 1
            print(f"  [Result] ❌ {tw_conf} ({mpwr_id}): No waiver link extracted")
            continue

        # Upload QR code to Supabase Storage
        qr_url = None
        if qr_bytes and tw_conf:
            qr_url = upload_qr_code(tw_conf, qr_bytes)

        # Update the reservation in Supabase
        updated = update_reservation_waiver_link(tw_conf, waiver_link, qr_url)

        if updated:
            success_count += 1
            success_details.append(f"{tw_conf} → {waiver_link}")
            print(f"  [Result] ✅ {tw_conf}: {waiver_link}")
            # Clear failure tracker on success
            _failure_tracker.pop(tw_conf, None)
        else:
            error_count += 1
            print(f"  [Result] ❌ {tw_conf}: DB update failed")

    # 4. Summary
    active_cooldowns = sum(1 for v in _failure_tracker.values() if v["failures"] >= MAX_FAILURES_BEFORE_COOLDOWN)
    print(f"\n[Daemon] Cycle complete: {success_count} scraped, {error_count} errors, {active_cooldowns} in cooldown.")

    # 5. Slack notification
    if success_count > 0:
        detail_list = "\n".join(f"  • {d}" for d in success_details[:10])
        _send_slack_notification(
            f"✅ *[WAIVER LINK SCRAPER]* Scraped {success_count} waiver link(s):\n{detail_list}"
        )

    if error_count > 0:
        _send_slack_notification(
            f"⚠️ *[WAIVER LINK SCRAPER]* {error_count} reservation(s) failed during waiver link scrape. "
            f"Check logs for details."
        )


def main():
    """Entry point: run the daemon synchronously."""
    print("=" * 60)
    print("  Epic 4x4 Adventures — Waiver Link Scraper Daemon")
    print(f"  Using login: {os.getenv('MPOWR_EMAIL', 'NOT SET')}")
    print(f"  Supabase: {os.getenv('SUPABASE_URL', 'NOT SET')[:40]}...")
    print(f"  Poll interval: {POLL_INTERVAL_PEAK}s (peak) / {POLL_INTERVAL_OFFPEAK}s (off-peak)")
    print("=" * 60)

    # Graceful shutdown
    def handle_shutdown(signum, frame):
        print("\n[Daemon] Shutting down...")
        _close_scraper()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Run an immediate sweep on startup
    print("\n[Startup] Running initial sweep...")
    try:
        run_scraper_cycle()
    except Exception as e:
        print(f"[Startup] Initial sweep failed (non-fatal): {e}")

    print("\n[Daemon] Polling loop started. Press Ctrl+C to exit.")
    try:
        while True:
            # Determine sleep duration based on time of day
            now = datetime.now(MDT)
            if OPERATING_HOURS[0] <= now.hour < OPERATING_HOURS[1]:
                sleep_seconds = POLL_INTERVAL_PEAK
            else:
                sleep_seconds = POLL_INTERVAL_OFFPEAK
                
            time.sleep(sleep_seconds)
            run_scraper_cycle()
    except (KeyboardInterrupt, SystemExit):
        _close_scraper()
        print("[Daemon] Waiver Link Scraper safely shut down.")


if __name__ == "__main__":
    main()
