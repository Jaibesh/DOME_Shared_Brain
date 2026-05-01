import sys, os, json
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent')
from dotenv import load_dotenv
load_dotenv(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent\.env')
from supabase import create_client

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Check if order IDs 5675001 and 5675002 exist anywhere
for oid in ["5675001", "5675002"]:
    r1 = supabase.table("reservations").select("tw_confirmation, guest_name, tw_order_id, tw_booking_ids").eq("tw_order_id", oid).execute()
    print(f"Order ID {oid} in tw_order_id: {r1.data}")
    
    r2 = supabase.table("reservations").select("tw_confirmation, guest_name, tw_order_id, tw_booking_ids").filter("tw_booking_ids", "cs", f"[{oid}]").execute()
    print(f"Order ID {oid} in tw_booking_ids: {r2.data}")

# Check by guest name
for name in ["Matthew Johnson", "Daniel Wegh"]:
    r3 = supabase.table("reservations").select("tw_confirmation, guest_name, tw_order_id, tw_booking_ids, activity_date").eq("guest_name", name).execute()
    print(f"Guest exact '{name}': {r3.data}")
    
    last = name.split()[1]
    r4 = supabase.table("reservations").select("tw_confirmation, guest_name, tw_order_id, tw_booking_ids, activity_date").ilike("guest_name", f"%{last}%").execute()
    for r in r4.data:
        print(f"  Fuzzy match: {r['tw_confirmation']} = {r['guest_name']} (date: {r['activity_date']}, order: {r['tw_order_id']}, bids: {r['tw_booking_ids']})")

# Also check the webhook payload from recon_webhooks
print("\n--- ERROR WEBHOOKS ---")
r5 = supabase.table("recon_webhooks").select("*").eq("status", "error").execute()
for w in r5.data:
    payload = w.get("payload", {})
    gn = payload.get("full_name", "")
    if "Johnson" in gn or "Wegh" in gn:
        print(f"\nWaiver for {gn}:")
        print(f"  bookings: {payload.get('bookings', [])}")
        print(f"  email: {payload.get('email', '')}")
        print(f"  waiver_type: {payload.get('waiver_type', {}).get('name', '')}")
        customer = payload.get("customer", {})
        print(f"  customer.bookings: {customer.get('bookings', [])}")
        print(f"  customer.full_name: {customer.get('full_name', '')}")
