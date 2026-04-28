"""
Use /api/trip/{CONF_CODE}/get to fetch booking IDs for the 5 remaining reservations
and update Supabase. Also update their activity_date if it changed (rescheduled).
"""
import os, sys, json, time
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()
import requests
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TW_BASE = "https://epic4x4.tripworks.com"
TW_COOKIE = "r4odf3um2rec2c36c722l81d5c"

tw = requests.Session()
tw.cookies.set("TripWorksSession-prod", TW_COOKIE, domain=".tripworks.com", path="/")
tw.headers.update({
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "X-Timezone": "America/Denver",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

real_missing = [
    "ZPEG-BYMX",
    "TCEU-MUQV",
    "RPSI-AFNX",
    "RPIE-MJBX",
    "IBPA-IAEU",
]

print("=== Fetching booking IDs via /api/trip/{code}/get ===\n")

for conf in real_missing:
    r = tw.get(f"{TW_BASE}/api/trip/{conf}/get", timeout=15)
    if r.status_code != 200:
        print(f"  FAIL: {conf} -> {r.status_code}")
        continue

    data = r.json()
    trip = data.get("trip", {})
    
    # Extract trip-level info
    trip_id = trip.get("id")
    customer = trip.get("customer", {})
    cust_name = f"{customer.get('first_name', '??')} {customer.get('last_name', '??')}"
    
    # Extract booking IDs from tripOrders
    booking_ids = []
    order_id = None
    trip_orders = trip.get("tripOrders", trip.get("trip_orders", []))
    
    for to in trip_orders:
        if not order_id:
            order_id = to.get("id")
        for b in to.get("bookings", []):
            bid = b.get("id")
            if bid and isinstance(bid, int):
                booking_ids.append(bid)
    
    # Extract the actual scheduled date from the experience_timeslot
    actual_date = None
    for to in trip_orders:
        ts = to.get("experience_timeslot", {})
        if ts:
            start = ts.get("start_date_time", "")
            if start:
                actual_date = start[:10]  # YYYY-MM-DD
                break
    
    print(f"  {conf} ({cust_name})")
    print(f"    Trip ID: {trip_id}")
    print(f"    Order ID: {order_id}")
    print(f"    Booking IDs: {booking_ids}")
    print(f"    Actual Date: {actual_date}")
    
    # Update Supabase
    if booking_ids:
        updates = {"tw_booking_ids": booking_ids}
        if order_id:
            updates["tw_order_id"] = str(order_id)
        if actual_date:
            # Check if the date changed (reservation was rescheduled)
            existing = supabase.table("reservations").select("activity_date").eq("tw_confirmation", conf).execute()
            if existing.data:
                old_date = existing.data[0].get("activity_date", "")
                if old_date != actual_date:
                    print(f"    ** Date changed: {old_date} -> {actual_date}")
                    updates["activity_date"] = actual_date
        
        try:
            supabase.table("reservations").update(updates).eq("tw_confirmation", conf).execute()
            print(f"    OK -> Supabase updated")
        except Exception as e:
            print(f"    ERROR: {e}")
    else:
        print(f"    WARNING: No booking IDs found!")

print("\n=== DONE ===")
