"""
Recovery script: Re-process all reservations that were created in MPOWR
but failed to push to Supabase due to the subtotal_dollars bug.

Uses the FULL webhook payload from pending_webhooks to populate all columns.
"""
import os
import sys
import json
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.tripworks_mapper import build_payloads_from_webhook, map_legacy_to_dashboard

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

# These are the reservations that were created in MPOWR but failed to push to Supabase
AFFECTED = {
    "SPQA-RTUB": "CO-JEJ-BZG",
    "HZUP-INPF": "CO-5MQ-369",
    "JJSE-DVGG": "CO-8KG-MDR",
    "RNBG-IEFY": "CO-AN8-5J5",
    "VIRP-JCDB": "CO-KD8-4NE",
}

_DASH_TO_SUPABASE = {
    "TW Confirmation": "tw_confirmation",
    "TW Order ID": "tw_order_id",
    "First Name": None,
    "Last Name": None,
    "Email": "email",
    "Phone": "phone",
    "Activity": "activity_name",
    "Activity Internal": "activity_internal",
    "Booking Type": "booking_type",
    "Ticket Type": "ticket_type",
    "Vehicle Model": "vehicle_model",
    "Vehicle Qty": "vehicle_qty",
    "Party Size": "party_size",
    "Activity Date": "activity_date",
    "Activity Time": "activity_time",
    "End Time": "end_time",
    "Normalized Date": None,
    "Rental Return Time": "rental_return_time",
    "Sub-Total": "sub_total",
    "Total": "total",
    "Amount Paid": "amount_paid",
    "Amount Due": "amount_due",
    "Adventure Assure": "adventure_assure",
    "Trip Safe": "trip_safe",
    "Deposit Status": "deposit_status",
    "Payment Collected By": "payment_collected_by",
    "Payment Notes": "payment_notes",
    "MPWR Confirmation Number": "mpwr_number",
    "MPWR Waiver Link": "mpwr_waiver_link",
    "MPWR Status": None,
    "Webhook Email": "webhook_email",
    "Primary Rider": "primary_rider",
    "Epic Waivers Expected": "epic_expected",
    "Epic Waivers Complete": "epic_complete",
    "Epic Waiver Names": "epic_names",
    "Polaris Waivers Expected": "polaris_expected",
    "Polaris Waivers Complete": "polaris_complete",
    "Polaris Waiver Names": "polaris_names",
    "OHV Required": "ohv_required",
    "OHV Permits Expected": "ohv_expected",
    "OHV Permits Uploaded": "ohv_complete",
    "OHV Permit Names": "ohv_permit_names",
    "OHV Uploaded": "ohv_uploaded",
    "OHV File Path": "ohv_file_path",
    "Rental Status": "rental_status",
    "Checked In": "checked_in",
    "Checked In At": "checked_in_at",
    "Checked In By": "checked_in_by",
    "TW Booking Link": "tw_link",
    "Customer Portal Link": "customer_portal_link",
    "Trip Method": "trip_method",
    "Notes": "notes",
    "Created At": "created_at",
    "Last Updated": "last_updated",
}

for tw_conf, mpwr_id in AFFECTED.items():
    print(f"\n--- Processing {tw_conf} (MPOWR: {mpwr_id}) ---")
    
    # Check if it already exists in the database
    existing = supabase.table("reservations").select("tw_confirmation").eq("tw_confirmation", tw_conf).execute()
    if existing.data:
        print(f"  Already exists in database. Checking if mpwr_number is set...")
        row = existing.data[0]
        # Just update the mpwr_number if missing
        supabase.table("reservations").update({"mpwr_number": mpwr_id}).eq("tw_confirmation", tw_conf).execute()
        print(f"  Updated mpwr_number to {mpwr_id}")
        continue
    
    # Pull the original webhook payload from pending_webhooks
    res = supabase.table("pending_webhooks").select("payload").eq("payload->>confirmation_code", tw_conf).limit(1).execute()
    if not res.data:
        print(f"  WARNING: No webhook payload found for {tw_conf}. Skipping.")
        continue
    
    webhook_data = res.data[0]
    payload = webhook_data["payload"]
    
    # Build payloads using the same mapper the Creator Agent uses
    creation_payloads = build_payloads_from_webhook({"_payload": payload})
    
    if not creation_payloads or creation_payloads[0].get("error"):
        err = creation_payloads[0].get("error") if creation_payloads else "No payload"
        print(f"  WARNING: Mapper returned error: {err}. Skipping.")
        continue
    
    primary_p = creation_payloads[0]
    adjusted_subtotal_dollars = primary_p.get("target_price", 0.0)
    
    # Build the dashboard row using the same logic as the Creator Agent
    row_for_dash = {
        "TW Confirmation": tw_conf,
        "First Name": primary_p["first_name"],
        "Last Name": primary_p["last_name"],
        "Email": payload.get("customer", {}).get("email", ""),
        "Phone": primary_p["phone"],
        "Activity": primary_p["activity"] + (" (+More)" if len(creation_payloads) > 1 else ""),
        "Activity Date": primary_p["activity_date"],
        "Activity Time": primary_p["activity_time"],
        "Ticket Type": "",
        "Party Size": primary_p.get("party_size", 1),
        "Sub-Total": adjusted_subtotal_dollars,
        "Notes": "",
        "has_adventure_assure": "adventure" in primary_p.get("insurance_label", "").lower(),
        "has_tripsafe": primary_p.get("has_tripsafe", False),
    }
    
    dashboard_row = map_legacy_to_dashboard(
        row=row_for_dash,
        mpwr_conf_number=mpwr_id,
        webhook_payload=payload,
    )
    
    # Convert to Supabase column names
    snake_row = {}
    for k, v in dashboard_row.items():
        sb_col = _DASH_TO_SUPABASE.get(k)
        if sb_col is None:
            continue
        if sb_col in ("ohv_required", "ohv_uploaded", "checked_in"):
            snake_row[sb_col] = str(v).strip().upper() == "TRUE"
        elif sb_col in ("epic_expected", "epic_complete", "polaris_expected", "polaris_complete",
                         "ohv_expected", "ohv_complete", "party_size", "vehicle_qty"):
            try:
                snake_row[sb_col] = int(v) if v else 0
            except (ValueError, TypeError):
                snake_row[sb_col] = 0
        elif sb_col in ("sub_total", "total", "amount_paid", "amount_due"):
            try:
                snake_row[sb_col] = float(str(v).replace("$", "").replace(",", "")) if v else 0.0
            except (ValueError, TypeError):
                snake_row[sb_col] = 0.0
        elif sb_col in ("epic_names", "polaris_names", "ohv_permit_names"):
            snake_row[sb_col] = [x.strip() for x in str(v).split(",")] if v else []
        elif sb_col in ("created_at", "last_updated", "checked_in_at"):
            snake_row[sb_col] = str(v) if v else None
        else:
            snake_row[sb_col] = str(v) if v is not None else ""
    
    # Build guest_name
    first = str(dashboard_row.get("First Name", "")).strip()
    last = str(dashboard_row.get("Last Name", "")).strip()
    snake_row["guest_name"] = f"{first} {last}".strip()
    
    # Extract TW booking IDs
    booking_ids = []
    for to in payload.get("tripOrders", []):
        for b in to.get("bookings", []):
            bid = b.get("id")
            if bid and isinstance(bid, int):
                booking_ids.append(bid)
    if booking_ids:
        snake_row["tw_booking_ids"] = booking_ids
    
    # Ensure MPOWR ID is set
    snake_row["mpwr_number"] = mpwr_id
    
    # Normalize dates to ISO format
    for date_field in ["activity_date"]:
        if date_field in snake_row and snake_row[date_field]:
            val = str(snake_row[date_field]).strip()
            if "/" in val:
                from datetime import datetime
                try:
                    snake_row[date_field] = datetime.strptime(val, "%m/%d/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass
    
    # Upsert
    try:
        supabase.table("reservations").upsert(snake_row, on_conflict="tw_confirmation").execute()
        print(f"  OK: Inserted {tw_conf} ({snake_row.get('guest_name', '?')}) with {len(snake_row)} columns")
    except Exception as e:
        print(f"  FAILED: {e}")

print("\n=== Recovery complete ===")
