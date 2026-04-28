"""
Deep-dive into TripWorks manifest to map confirmation_code -> booking IDs.
"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')

COOKIE_NAME = "TripWorksSession-prod"
COOKIE_VALUE = "r4odf3um2rec2c36c722l81d5c"
BASE = "https://epic4x4.tripworks.com"

session = requests.Session()
session.cookies.set(COOKIE_NAME, COOKIE_VALUE, domain=".tripworks.com", path="/")
session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "X-Timezone": "America/Denver",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
})

r = session.post(f"{BASE}/api/manifest/getManifestOnDay/2026-04-28", json={}, timeout=30)
data = r.json()

print("=== Mapping: confirmation_code -> booking IDs ===\n")
for trip_order in data.get("tripOrders", []):
    to_id = trip_order.get("id")
    trip = trip_order.get("trip", {})
    
    # Find confirmation code
    conf_code = trip.get("confirmation_code", trip.get("confirmationCode", "??"))
    customer = trip.get("customer", {})
    cust_name = f"{customer.get('first_name', '??')} {customer.get('last_name', '??')}" if customer else "??"
    
    # If no conf code in trip, check trip_order level
    if conf_code == "??":
        conf_code = trip_order.get("confirmation_code", trip_order.get("confirmationCode", "??"))
    
    # Get booking IDs
    bookings = trip_order.get("bookings", [])
    booking_ids = [b.get("id") for b in bookings]
    
    print(f"  TripOrder {to_id} | Conf: {conf_code} | Customer: {cust_name}")
    print(f"    Booking IDs: {booking_ids}")
    
    # Show trip keys for first one
    if trip_order == data["tripOrders"][0]:
        print(f"\n    --- FIRST TRIP DETAIL ---")
        print(f"    trip keys: {list(trip.keys())[:20]}")
        print(f"    trip.id: {trip.get('id')}")
        # Look through ALL trip keys for confirmation code
        for k, v in trip.items():
            if isinstance(v, str) and ('-' in v or len(v) == 9):
                print(f"    trip.{k} = {v}")
        print(f"    booking[0] keys: {list(bookings[0].keys())[:20] if bookings else 'NONE'}")
        if bookings:
            b = bookings[0]
            for k, v in b.items():
                if not isinstance(v, (dict, list)):
                    print(f"    booking[0].{k} = {v}")
        print()
