"""
diagnose_status_webhooks.py — Investigate why status webhooks aren't updating the dashboard.
Checks: deployment health, booking ID coverage, DB state, and live endpoint test.
"""
import os, sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Waiver_Dashboard', 'backend', '.env'))
from supabase import create_client

RAILWAY_URL = "https://epic-waiver-dashboard-production.up.railway.app"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

print("=" * 70)
print("STATUS WEBHOOK DIAGNOSTIC REPORT")
print("=" * 70)

# ─── 1. Check Railway is alive and deployed ───
print("\n[1] Railway Health Check...")
try:
    r = requests.get(f"{RAILWAY_URL}/api/health", timeout=10)
    print(f"    Status: {r.status_code}")
    print(f"    Response: {r.json()}")
except Exception as e:
    print(f"    ❌ FAILED: {e}")
    print("    Railway may not have finished deploying yet!")

# ─── 2. Check if the endpoint exists ───
print("\n[2] Status Webhook Endpoint Test (OPTIONS)...")
try:
    r = requests.options(f"{RAILWAY_URL}/api/webhook/tw-status-changed", timeout=10)
    print(f"    Status: {r.status_code}")
except Exception as e:
    print(f"    ❌ FAILED: {e}")

# ─── 3. Send a test webhook with a KNOWN booking ID ───
print("\n[3] Sending Test Status Webhook...")

# Find a reservation with booking IDs
res = sb.table('reservations') \
    .select('tw_confirmation, guest_name, tw_booking_ids, tw_status, activity_date') \
    .neq('tw_booking_ids', '[]') \
    .order('activity_date', desc=True) \
    .limit(3) \
    .execute()

if res.data:
    for row in res.data:
        print(f"    Has booking IDs: {row['tw_confirmation']} ({row['guest_name']}) "
              f"IDs={row['tw_booking_ids']} tw_status='{row.get('tw_status','')}'")
else:
    print("    ⚠️ NO reservations have tw_booking_ids populated!")

# Actually send a test payload
test_payload = {
    "id": 99999999,  # Fake booking ID — should NOT match anything
    "created_at": "2026-04-25T17:00:00+00:00",
    "status": {"id": 15, "name": "Checked In"},
    "customer": {
        "full_name": "Test Diagnostic User",
        "first_name": "Test",
        "last_name": "Diagnostic",
        "email": "test@test.com"
    },
    "experience_customer_type": {"id": 195, "name": "Adult"},
    "trip_order": {
        "experience": {"id": 105, "name": "Diagnostic Test"},
        "experience_timeslot": {
            "start_time": "2026-04-25T16:00:00+00:00",
            "end_time": "2026-04-25T17:00:00+00:00"
        }
    },
    "custom_field_values": [],
    "is_complimentary": False
}

try:
    r = requests.post(f"{RAILWAY_URL}/api/webhook/tw-status-changed", json=test_payload, timeout=15)
    print(f"    Response: {r.status_code} -> {r.text[:300]}")
except Exception as e:
    print(f"    ❌ POST FAILED: {e}")

# ─── 4. Check booking ID coverage ───
print("\n[4] Booking ID Coverage...")
all_res = sb.table('reservations').select('tw_confirmation, tw_booking_ids, tw_status, activity_date').execute()
all_rows = all_res.data or []
total = len(all_rows)
has_ids = [r for r in all_rows if r.get('tw_booking_ids') and len(r['tw_booking_ids']) > 0]
has_status = [r for r in all_rows if r.get('tw_status') and r['tw_status'] not in ('', 'Not Checked In')]

print(f"    Total reservations: {total}")
print(f"    With booking IDs: {len(has_ids)} ({100*len(has_ids)//max(total,1)}%)")
print(f"    With tw_status set: {len(has_status)}")

if has_status:
    for r in has_status[:5]:
        print(f"      -> {r['tw_confirmation']}: tw_status='{r['tw_status']}'")

# ─── 5. Check today's reservations specifically ───
print("\n[5] Today's Reservations — Booking ID Status...")
from datetime import date
today = date.today().strftime("%m/%d/%Y")
today_iso = date.today().isoformat()  # 2026-04-25

today_res = sb.table('reservations') \
    .select('tw_confirmation, guest_name, tw_booking_ids, tw_status, activity_date, activity_time') \
    .or_(f'activity_date.eq.{today},activity_date.eq.{today_iso},normalized_date.eq.{today}') \
    .order('activity_time') \
    .execute()

today_rows = today_res.data or []
print(f"    Today's reservations: {len(today_rows)}")
with_ids = [r for r in today_rows if r.get('tw_booking_ids') and len(r['tw_booking_ids']) > 0]
without_ids = [r for r in today_rows if not r.get('tw_booking_ids') or len(r['tw_booking_ids']) == 0]
print(f"    With booking IDs: {len(with_ids)}")
print(f"    WITHOUT booking IDs: {len(without_ids)} ← These CANNOT be matched by booking ID!")

if without_ids:
    print("\n    Reservations missing booking IDs (first 10):")
    for r in without_ids[:10]:
        print(f"      {r['tw_confirmation']} - {r['guest_name']} @ {r.get('activity_time','?')}")

# ─── 6. Check the status webhook endpoint response for detailed errors ───
print("\n[6] Root Cause Analysis...")

if len(has_ids) < total * 0.5:
    print(f"""
    ⚠️ ROOT CAUSE LIKELY: Only {len(has_ids)}/{total} ({100*len(has_ids)//max(total,1)}%) of reservations 
    have tw_booking_ids populated. The status webhook matches by booking ID.
    
    When TripWorks sends a status change for booking_id=5636924, we search:
      SELECT * FROM reservations WHERE tw_booking_ids @> '[5636924]'
    
    If the reservation doesn't have that booking ID stored, the match FAILS
    and falls back to customer name matching (which may also fail if names differ).
    
    FIX: We need to backfill booking IDs for ALL reservations, not just the 28 
    that had webhook data available.
    """)

print("=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
