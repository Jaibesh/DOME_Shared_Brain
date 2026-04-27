"""
Quick single-reservation dry-run to verify MPOWR UI hasn't changed.
Uses a Hell's Revenge Pro R test case — the most common booking type.
"""
import os, sys, time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

from datetime import datetime, timedelta
from mpowr_creator_bot import MpowrCreatorBot
from data_mapper import build_customer_payload_from_row

# Use a date 5 days out to ensure availability
test_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

row = {
    "First Name": "VALIDATION",
    "Last Name": "TEST",
    "Phone": "555-000-0000",
    "TW Confirmation": "CO-VALIDATION-01",
    "Activity": "Gateway to Hell's Revenge and Fins N' Things",
    "Ticket Type": "2026 RZR Pro R for 1 - 2 People x1",
    "Activity Date": test_date,
    "Activity Time": "9:00 AM",
    "Sub-Total": "205",
    "Normalized Date": test_date,
}

print(f"[Validation] Building payload for Hell's Revenge Pro R on {test_date}...")
payload = build_customer_payload_from_row(row, 999)

if payload.get("error"):
    print(f"PAYLOAD ERROR: {payload['error']}")
    sys.exit(1)

print(f"  Activity: {payload['mpowr_activity']}")
print(f"  Vehicle:  {payload['mpowr_vehicle']} x{payload['vehicle_qty']}")
print(f"  Guides:   {payload.get('guide_addons')}")
print(f"  Price:    ${payload['target_price']:.2f}")
print(f"  Email:    {payload['webhook_email']}")

print(f"\n[Validation] Starting MPOWR bot (HEADED, DRY_RUN=true)...")
bot = MpowrCreatorBot(
    email=os.getenv("MPOWR_EMAIL"),
    password=os.getenv("MPOWR_PASSWORD"),
    headless=False,  # HEADED so you can watch
    dry_run=True,
)

start = time.time()
try:
    bot._start_browser()
    print(f"[Validation] Logged in. Running reservation...")
    result = bot.create_reservation(payload)
    elapsed = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"RESULT: {result.status} ({elapsed:.1f}s)")
    if result.error_message:
        print(f"MESSAGE: {result.error_message}")
    if result.screenshot_path:
        print(f"SCREENSHOT: {result.screenshot_path}")
    print(f"{'='*60}")
    
    if result.status == "dry_run":
        print(f"\n✅ MPOWR UI validated! Form fills correctly in {elapsed:.1f}s")
    else:
        print(f"\n❌ Something went wrong. Check the screenshot above.")
finally:
    bot._close_browser()
