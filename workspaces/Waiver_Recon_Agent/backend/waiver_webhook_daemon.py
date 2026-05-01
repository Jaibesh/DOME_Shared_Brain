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
        
        import difflib
        
        clean_name = re.sub(r'\s*\(\d+.*?\)\s*$', '', signer_name).strip().lower()
        existing_clean = [re.sub(r'\s*\(\d+.*?\)\s*$', '', n).strip().lower() for n in current_names]
        
        for e_clean in existing_clean:
            if clean_name == e_clean or difflib.SequenceMatcher(None, clean_name, e_clean).ratio() > 0.8:
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

    # Extract Order ID (booking-level ID from the waiver payload)
    order_id = ""
    if "bookings" in body and isinstance(body["bookings"], list) and len(body["bookings"]) > 0:
        order_id = str(body["bookings"][0].get("id", ""))
    elif "customer" in body and "bookings" in body["customer"] and isinstance(body["customer"]["bookings"], list) and len(body["customer"]["bookings"]) > 0:
        order_id = str(body["customer"]["bookings"][0].get("id", ""))

    # Extract additional matching fields from the payload
    experience_name = body.get("experience_name", "")
    guest_last_name = body.get("last_name", "")

    # Resolve TW Confirmation Code
    if not guest_name and not order_id:
        raise ValueError("Payload missing guest name and order ID")

    supabase = get_supabase()
    target_conf = None
    target_row = None

    # ── Layer 1: Booking ID in tw_booking_ids (fastest, most precise) ──
    if order_id:
        try:
            res = supabase.table("reservations").select("*") \
                .filter("tw_booking_ids", "cs", f"[{order_id}]") \
                .execute()
            if res.data:
                target_row = res.data[0]
                target_conf = str(target_row.get("tw_confirmation", "")).strip()
                print(f"  [Match] Layer 1 HIT: booking_id {order_id} -> {target_conf}")
        except Exception as e:
            print(f"  [Match] Layer 1 error: {e}")

    # ── Layer 2: Exact guest name match (primary booker) ──
    if not target_conf and guest_name:
        try:
            res = supabase.table("reservations").select("*") \
                .eq("guest_name", guest_name.strip()) \
                .gte("activity_date", (datetime.now(MDT) - timedelta(days=7)).date().isoformat()) \
                .execute()
            if res.data:
                target_row = res.data[0]
                target_conf = str(target_row.get("tw_confirmation", "")).strip()
                print(f"  [Match] Layer 2 HIT: exact name '{guest_name}' -> {target_conf}")
        except Exception as e:
            print(f"  [Match] Layer 2 error: {e}")

    # ── Layer 3: Email match against reservation email column ──
    if not target_conf and guest_email:
        try:
            res = supabase.table("reservations").select("*") \
                .eq("email", guest_email) \
                .gte("activity_date", (datetime.now(MDT) - timedelta(days=7)).date().isoformat()) \
                .execute()
            if res.data:
                target_row = res.data[0]
                target_conf = str(target_row.get("tw_confirmation", "")).strip()
                print(f"  [Match] Layer 3 HIT: email '{guest_email}' -> {target_conf}")
        except Exception as e:
            print(f"  [Match] Layer 3 error: {e}")

    # ── Layer 4: Last name fuzzy match + upcoming date (catches family/group riders) ──
    if not target_conf and guest_last_name and len(guest_last_name) >= 3:
        try:
            res = supabase.table("reservations").select("*") \
                .gte("activity_date", (datetime.now(MDT) - timedelta(days=2)).date().isoformat()) \
                .ilike("guest_name", f"%{guest_last_name.strip()}%") \
                .execute()
            if res.data:
                target_row = res.data[0]
                target_conf = str(target_row.get("tw_confirmation", "")).strip()
                print(f"  [Match] Layer 4 HIT: last name '{guest_last_name}' -> {target_conf} ({target_row.get('guest_name')})")
        except Exception as e:
            print(f"  [Match] Layer 4 error: {e}")

    # ── Layer 5: Experience name + upcoming date (broadest — matches by activity) ──
    if not target_conf and experience_name:
        try:
            res = supabase.table("reservations").select("*") \
                .gte("activity_date", (datetime.now(MDT) - timedelta(days=2)).date().isoformat()) \
                .ilike("activity_name", f"%{experience_name.strip()}%") \
                .execute()
            if res.data:
                # Try to narrow by last name if available
                if guest_last_name:
                    for r in res.data:
                        if guest_last_name.lower() in str(r.get("guest_name", "")).lower():
                            target_row = r
                            target_conf = str(r.get("tw_confirmation", "")).strip()
                            break
                if not target_conf:
                    target_row = res.data[0]
                    target_conf = str(target_row.get("tw_confirmation", "")).strip()
                print(f"  [Match] Layer 5 HIT: experience '{experience_name}' -> {target_conf}")
        except Exception as e:
            print(f"  [Match] Layer 5 error: {e}")

    # ── Layer 6: Email-only fallback (no date constraint — last resort for legacy) ──
    if not target_conf and guest_email:
        try:
            res = supabase.table("reservations").select("*") \
                .eq("email", guest_email) \
                .order("activity_date", desc=True) \
                .limit(1) \
                .execute()
            if res.data:
                target_row = res.data[0]
                target_conf = str(target_row.get("tw_confirmation", "")).strip()
                print(f"  [Match] Layer 6 HIT: email-only '{guest_email}' -> {target_conf}")
        except Exception as e:
            print(f"  [Match] Layer 6 error: {e}")

    if target_conf and target_row:
        # Self-Healing: backfill booking ID for future Layer-1 fast-path matching
        if order_id:
            existing_ids = target_row.get("tw_booking_ids") or []
            if int(order_id) not in existing_ids:
                try:
                    new_ids = existing_ids + [int(order_id)]
                    supabase.table("reservations").update({"tw_booking_ids": new_ids}).eq("tw_confirmation", target_conf).execute()
                    print(f"  [Self-Healing] Backfilled booking_id={order_id} into {target_conf}")
                except Exception:
                    pass

        # Execute Self-Healing Framework (email, phone, party size)
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
