import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'MPWR_Reservation_Agent'))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'MPWR_Reservation_Agent', '.env'))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', '.env'), override=False)

from supabase import create_client
from sheets import get_sheets_client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
sb = create_client(url, key)

print("Starting Backfill for Booking Type & Waivers...")

client = get_sheets_client()
dash_id = os.getenv("DASHBOARD_SHEET_ID")
dash_sheet = client.open_by_key(dash_id).sheet1
dash_records = dash_sheet.get_all_records()

def safe_int(val):
    if not val: return 0
    try: return int(float(str(val).strip() or 0))
    except: return 0

updates_made = 0
errors = 0

print(f"Found {len(dash_records)} records in Google Sheet. Processing...")

for i, r in enumerate(dash_records):
    tc = str(r.get("TW Confirmation", "")).strip().upper()
    if not tc:
        continue
        
    # Calculate correct booking type based on Activity string
    act = str(r.get("Activity", "")).lower()
    if any(t in act for t in ["hell's", "poison spider", "discovery", "pro xperience", "tripadvisor", "gateway"]):
        booking_type = "Tour"
    elif any(t in act for t in ["rental", "hour", "day", "self-guided", "rzr", "pro s", "pro r", "xp s", "ultimate"]):
        booking_type = "Rental"
    else:
        booking_type = "Tour"
        
    update_data = {
        "booking_type": booking_type,
        "epic_expected": safe_int(r.get("Epic Waivers Expected", 0)),
        "epic_complete": safe_int(r.get("Epic Waivers Complete", 0)),
        "polaris_expected": safe_int(r.get("Polaris Waivers Expected", 0)),
        "polaris_complete": safe_int(r.get("Polaris Waivers Complete", 0)),
        "ohv_expected": safe_int(r.get("OHV Permits Expected", 0)),
        "ohv_complete": safe_int(r.get("OHV Permits Uploaded", 0)), # Mapping 'Uploaded' from sheets to 'complete' in DB
        "ohv_uploaded": str(r.get("OHV Uploaded", "FALSE")).strip().upper() == "TRUE"
    }
    
    try:
        res = sb.table("reservations").update(update_data).eq("tw_confirmation", tc).execute()
        if res.data:
            updates_made += 1
            if updates_made % 50 == 0:
                print(f"  ... updated {updates_made} records")
    except Exception as e:
        print(f"Error updating {tc}: {e}")
        errors += 1

print(f"\nBackfill Complete!")
print(f"Successfully updated: {updates_made} records")
print(f"Errors: {errors}")
