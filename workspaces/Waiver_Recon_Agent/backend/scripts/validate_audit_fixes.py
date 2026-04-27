# -*- coding: utf-8 -*-
"""Quick validation of all audit bug fixes."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from data_mapper import build_customer_payload_from_row, parse_subtotal
from sheets import _parse_activity_date
from datetime import date

print("=" * 60)
print("AUDIT FIX VALIDATION")
print("=" * 60)

# BUG-3/BUG-4: Test that M/D/YYYY dates get stripped of time portion
test_row = {
    "First Name": "Test", "Last Name": "User",
    "Activity": "Gateway to Hell's Revenge and Fins N' Things",
    "Activity Date": "5/6/2026 5:15:00 PM",
    "Activity Time": "9:00:00 AM",
    "Ticket Type": "2026 RZR Pro R for 1 - 2 People x1",
    "TW Confirmation": "CO-TEST-01",
    "Sub-Total": "$411.00",
    "Phone": "555-1234",
    "MPWR Confirmation Number": "",
}
payload = build_customer_payload_from_row(test_row, 5)
activity_date = payload["activity_date"]
print(f"  BUG-4 activity_date: {activity_date!r}")
assert "5:15" not in activity_date, "BUG-4 FAIL: Time should be stripped!"
assert payload.get("error") is None, f"Payload error: {payload.get('error')}"
print(f"  target_price: {payload['target_price']}")
print(f"  mpowr_activity: {payload['mpowr_activity']}")
print(f"  mpowr_vehicle: {payload['mpowr_vehicle']}")
print("  [OK] BUG-4 date stripping")

# BUG-3: Test various date formats
for d, expected in [
    ("5/6/2026", date(2026, 5, 6)),
    ("2026-04-18", date(2026, 4, 18)),
    ("4/24/2026 1:00 PM", date(2026, 4, 24)),
    ("04/02/2026", date(2026, 4, 2)),
]:
    result = _parse_activity_date(d)
    assert result == expected, f"BUG-3 FAIL: {d} => {result} (expected {expected})"
    print(f"  [OK] BUG-3 date parse: {d} => {result}")

# EDGE-9: past-date detection
past = _parse_activity_date("3/31/2026")
today = date.today()
assert past < today, f"EDGE-9 FAIL: 3/31/2026 should be past (today={today})"
print(f"  [OK] EDGE-9 past filter: 3/31/2026 ({past}) < {today}")

# parse_subtotal
for val, expected in [("$411.00", 411.0), ("$1,855.00", 1855.0), (185500, 1855.0), ("95", 95.0)]:
    result = parse_subtotal(val)
    assert result == expected, f"parse_subtotal FAIL: {val} => {result} (expected {expected})"
    print(f"  [OK] parse_subtotal: {val!r} => ${result}")

print()
print("=" * 60)
print("ALL VALIDATION TESTS PASS")
print("=" * 60)
