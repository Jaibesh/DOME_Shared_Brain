"""
waiver_webhook_daemon.py — Standalone Webhook Queue Processor

Polls the 'recon_webhooks' Supabase table every 60 seconds for pending webhooks.
Specifically processes 'waiver.completed' events, executing a Self-Healing Data
check against the main reservations table, and extracting the signer's name and age.

Usage:
    python waiver_webhook_daemon.py
"""

import os
import sys
import time
import json
import re
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv, find_dotenv

from waiver_link_storage import get_supabase
from slack_notifier import SlackNotifier

load_dotenv(find_dotenv())
MDT = pytz.timezone("America/Denver")

POLL_INTERVAL = 60  # Poll every 60 seconds
slack = SlackNotifier()

def _self_heal_database(row: dict, webhook_payload: dict, target_conf: str) -> list:
    """
    Check if the database row is missing any crucial data that is present in the webhook payload.
    If so, patch it silently and return a list of patched fields for logging.
    """
    updates = {}
    patched_fields = []
    
    # 1. Email
    current_email = str(row.get("email") or "").strip()
    webhook_email = (webhook_payload.get("email") or webhook_payload.get("customer", {}).get("email") or "").strip()
    if not current_email and webhook_email:
        updates["email"] = webhook_email
        patched_fields.append("email")
        
    # 2. Phone
    current_phone = str(row.get("phone") or "").strip()
    webhook_phone = (webhook_payload.get("phone") or webhook_payload.get("customer", {}).get("phone") or "").strip()
    if not current_phone and webhook_phone:
        updates["phone"] = webhook_phone
        patched_fields.append("phone")
        
    # 3. Party Size / Expected Waivers Fallback
    current_party_size = int(row.get("party_size") or 0)
    if current_party_size == 0:
        bookings = webhook_payload.get("bookings") or webhook_payload.get("customer", {}).get("bookings", [])
        if bookings and isinstance(bookings, list):
            b = bookings[0]
            webhook_party = b.get("pax_count", 0)
            if webhook_party > 0:
                updates["party_size"] = webhook_party
                patched_fields.append("party_size")
                if int(row.get("epic_expected") or 0) == 0:
                    updates["epic_expected"] = webhook_party
                    patched_fields.append("epic_expected")
                if int(row.get("polaris_expected") or 0) == 0:
                    updates["polaris_expected"] = webhook_party
                    patched_fields.append("polaris_expected")

    if updates:
        try:
            supabase = get_supabase()
            supabase.table("reservations").update(updates).eq("tw_confirmation", target_conf).execute()
            print(f"[Self-Healing] Patched missing legacy data for {target_conf}: {patched_fields}")
        except Exception as e:
            print(f"[Self-Healing] Failed to patch data for {target_conf}: {e}")
            
    return patched_fields

def increment_waiver_count(tw_conf: str, waiver_type: str, signer_name: str) -> bool:
    try:
        supabase = get_supabase()
        res = supabase.table("reservations").select("*").eq("tw_confirmation", tw_conf).execute()
        if not res.data:
            return False
        
        row = res.data[0]
        count_col = f"{waiver_type}_complete"
        names_col = f"{waiver_type}_names"
        
        current_count = row.get(count_col, 0) or 0
        current_names = row.get(names_col, []) or []
        
        clean_name = re.sub(r'\s*\(\d+.*?\)\s*$', '', signer_name).strip().lower()
        existing_clean = [re.sub(r'\s*\(\d+.*?\)\s*$', '', n).strip().lower() for n in current_names]
        
        if clean_name in existing_clean:
            return True # Already signed
        
        new_names = current_names + [signer_name]
        updates = {
            count_col: current_count + 1,
            names_col: new_names,
            "last_updated": datetime.now(MDT).isoformat()
        }
        
        supabase.table("reservations").update(updates).eq("tw_confirmation", tw_conf).execute()
        return True
    except Exception as e:
        print(f"[SupabaseData] Error incrementing waiver: {e}")
        return False

def process_waiver_completed(body: dict, db_record_id: str):
    """Processes a single 'waiver.completed' webhook payload."""
    guest_name = body.get("full_name") or body.get("customer", {}).get("full_name", "")
    guest_email = (body.get("email") or body.get("customer", {}).get("email", "") or "").strip().lower()

    # Extract DOB and calculate age
    dob_str = body.get("dob", "")
    age_str = ""
    is_minor = False
    if dob_str:
        try:
            dob = datetime.fromisoformat(dob_str.replace("+00:00", "+00:00"))
            today = datetime.now(MDT)
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            age_str = str(age)
            is_minor = not body.get("is_waiver_adult", True)
        except Exception as e:
            print(f"[{db_record_id}] DOB parse error: {e}")

    # Build explicit name with age
    name_with_age = guest_name
    if age_str:
        minor_flag = " ⚠️MINOR" if is_minor else ""
        name_with_age = f"{guest_name} ({age_str}{minor_flag})"

    # Grab Waiver Type
    waiver_type_name = body.get("waiver_type", {}).get("name", "").lower()
    w_type = "polaris" if "polaris" in waiver_type_name else "epic"

    # Extract Order ID
    order_id = ""
    if "bookings" in body and isinstance(body["bookings"], list) and len(body["bookings"]) > 0:
        order_id = str(body["bookings"][0].get("id", ""))
    elif "customer" in body and "bookings" in body["customer"] and isinstance(body["customer"]["bookings"], list) and len(body["customer"]["bookings"]) > 0:
        order_id = str(body["customer"]["bookings"][0].get("id", ""))

    # Resolve TW Confirmation Code
    if not guest_name and not order_id:
        raise ValueError("Payload missing guest name and order ID")

    supabase = get_supabase()
    
    # Scale Fix: Only pull recent/upcoming reservations to avoid loading the entire database into memory
    thirty_days_ago = (datetime.now(MDT) - timedelta(days=30)).date().isoformat()
    res = supabase.table("reservations").select("*").gte("activity_date", thirty_days_ago).execute()
    records = res.data
    
    target_conf = None
    target_row = None
    guest_clean = guest_name.strip().lower()
    
    for row in records:
        row_order = str(row.get("tw_order_id", "")).strip()
        booking_ids = [str(bid) for bid in row.get("tw_booking_ids", [])]

        if order_id and (row_order == order_id or order_id in booking_ids):
            target_conf = str(row.get("tw_confirmation", "")).strip()
            target_row = row
            break
            
        guest = str(row.get("guest_name", "")).strip().lower()
        if guest_clean and guest == guest_clean:
            target_conf = str(row.get("tw_confirmation", "")).strip()
            target_row = row
            break

        row_email = str(row.get("webhook_email", "") or "").strip().lower()
        if guest_email and row_email and guest_email == row_email:
            target_conf = str(row.get("tw_confirmation", "")).strip()
            target_row = row
            break

    if target_conf and target_row:
        # Execute Self-Healing Framework
        healed_fields = _self_heal_database(target_row, body, target_conf)
        
        # Increment Waiver Count
        success = increment_waiver_count(target_conf, w_type, name_with_age)
        if success:
            msg = f"✅ *Waiver Completed*\nCustomer: {name_with_age}\nTW Conf: {target_conf}"
            if healed_fields:
                msg += f"\n🩹 *Self-Healed Fields*: {', '.join(healed_fields)}"
            slack._send_message(None, msg)
            return True
        else:
            raise ValueError(f"Failed to increment waiver count for {target_conf}")
    else:
        raise ValueError(f"No matching reservation exists in Supabase for '{guest_name}' (Order: {order_id}). Tip: Verify this order ID is populated in the 'tw_order_id' or 'tw_booking_ids' column for this guest!")

def run_polling_cycle():
    """Polls recon_webhooks for pending tasks and processes them."""
    try:
        supabase = get_supabase()
        res = supabase.table("recon_webhooks").select("*").eq("status", "pending").order("created_at").execute()
        pending = res.data
    except Exception as e:
        print(f"[Daemon] Error querying Supabase: {e}")
        return

    if not pending:
        return

    print(f"\n[{datetime.now(MDT).strftime('%I:%M:%S %p')}] Found {len(pending)} pending specialized webhooks.")

    for record in pending:
        record_id = record["id"]
        w_type = record.get("webhook_type", "unknown")
        payload = record.get("payload", {})
        
        print(f"  -> Processing {record_id} ({w_type})...")
        
        try:
            if w_type == "waiver.completed":
                process_waiver_completed(payload, record_id)
            else:
                # In the future, add payment.completed, trip.updated here
                print(f"     Warning: Unknown webhook type '{w_type}'. Marking as processed to prevent blocking.")
            
            # Mark as processed
            supabase.table("recon_webhooks").update({
                "status": "processed",
                "processed_at": datetime.now(MDT).isoformat()
            }).eq("id", record_id).execute()
            print(f"     Done.")
            
        except Exception as e:
            err_msg = str(e)
            print(f"     [ERROR] {err_msg}")
            supabase.table("recon_webhooks").update({
                "status": "error",
                "error_message": err_msg,
                "processed_at": datetime.now(MDT).isoformat()
            }).eq("id", record_id).execute()
            slack._send_message(None, f"❌ *Webhook Processing Error* ({w_type})\nID: {record_id}\nError: {err_msg}")

def main():
    print("=" * 60)
    print("  Epic 4x4 Adventures — Specialized Webhook Daemon")
    print(f"  Supabase: {os.getenv('SUPABASE_URL', 'NOT SET')[:40]}...")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print("=" * 60)

    try:
        while True:
            run_polling_cycle()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[Daemon] Shutting down cleanly.")

if __name__ == "__main__":
    main()
