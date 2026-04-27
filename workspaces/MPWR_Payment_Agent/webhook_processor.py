import os
from dotenv import load_dotenv

load_dotenv()

import json
import time
from datetime import datetime, timezone
from supabase import create_client, Client
from bot_logger import get_bot_logger
from mpowr_payment_bot import process_settlement

log = get_bot_logger()

_supabase_client = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        _supabase_client = create_client(url, key)
    return _supabase_client

def process_payment_webhooks():
    """
    Polls pending_payment_webhooks, updates reservation balances,
    and settles in MPOWR if amount_due == 0.
    """
    log.info("Checking for pending payment webhooks...")
    supabase = get_supabase()

    MAX_RETRY_AGE_HOURS = 24  # Stop retrying webhooks older than 24 hours

    try:
        resp = supabase.table("pending_payment_webhooks") \
            .select("*") \
            .in_("status", ["pending", "retry"]) \
            .order("created_at", desc=False) \
            .limit(20) \
            .execute()
        webhooks = resp.data
    except Exception as e:
        log.error(f"Failed to fetch webhooks: {e}")
        return

    if not webhooks:
        return

    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_RETRY_AGE_HOURS)

    for wh in webhooks:
        wh_id = wh["id"]
        payload = wh.get("payload", {})
        
        # Expire webhooks stuck in retry for too long
        created_str = wh.get("created_at", "")
        if wh.get("status") == "retry" and created_str:
            try:
                created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created_dt < cutoff:
                    log.warning(f"Webhook {wh_id} expired (>{MAX_RETRY_AGE_HOURS}h old). Marking failed.")
                    mark_webhook_status(supabase, wh_id, "failed")
                    continue
            except Exception:
                pass
        
        # We only process if it's a payment direction
        direction = payload.get("direction", {}).get("name")
        if direction != "Payment":
            log.warning(f"Webhook {wh_id} is not a Payment direction. Marking processed.")
            mark_webhook_status(supabase, wh_id, "processed")
            continue
            
        trip_data = payload.get("trip", {})
        tw_conf = trip_data.get("confirmation_code")
        if not tw_conf:
            log.warning(f"Webhook {wh_id} missing tw_confirmation. Marking failed.")
            mark_webhook_status(supabase, wh_id, "failed")
            continue

        amount_paid = float(trip_data.get("paid", 0)) / 100.0  # tripworks sends cents
        amount_due = float(trip_data.get("due", 0)) / 100.0

        customer = trip_data.get("customer", {})
        email = customer.get("email")
        phone = customer.get("phone_format_intl") or customer.get("phone_format_164")

        # Get existing reservation
        try:
            res_resp = supabase.table("reservations").select("*").eq("tw_confirmation", tw_conf).execute()
            res_data = res_resp.data
        except Exception as e:
            log.error(f"DB Error fetching reservation {tw_conf}: {e}")
            continue

        if not res_data:
            # Reservation not created yet, retry later
            log.info(f"Reservation {tw_conf} not found in DB. Setting to retry.")
            mark_webhook_status(supabase, wh_id, "retry")
            continue

        reservation = res_data[0]
        mpwr_id = reservation.get("mpwr_number")
        if not mpwr_id or str(mpwr_id).strip().upper() == "UNKNOWN":
            log.info(f"Reservation {tw_conf} has no valid MPOWR ID yet ({mpwr_id}). Setting to retry.")
            mark_webhook_status(supabase, wh_id, "retry")
            continue

        mpwr_payment_settled = reservation.get("mpwr_payment_settled", False)

        # Update DB with new financial data & missing guest details if any
        update_data = {
            "amount_paid": amount_paid,
            "amount_due": amount_due,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
        # Append to notes if email/phone missing
        notes = reservation.get("notes") or ""
        if email and email not in notes:
            notes += f"\nEmail: {email}"
        if phone and phone not in notes:
            notes += f"\nPhone: {phone}"
        if notes != reservation.get("notes"):
            update_data["notes"] = notes.strip()

        try:
            supabase.table("reservations").update(update_data).eq("tw_confirmation", tw_conf).execute()
            log.info(f"[{tw_conf}] Updated DB: due=${amount_due:.2f}, paid=${amount_paid:.2f}")
        except Exception as e:
            log.error(f"[{tw_conf}] DB Error updating reservation: {e}")

        # Settle in MPOWR if due is 0
        if amount_due == 0 and not mpwr_payment_settled:
            activity_date_str = reservation.get("activity_date")
            if activity_date_str:
                try:
                    import pytz
                    act_date = datetime.strptime(activity_date_str, "%Y-%m-%d").date()
                    today = datetime.now(pytz.timezone('America/Denver')).date()
                    if act_date < today:
                        log.info(f"[{tw_conf}] Activity date {act_date} is in the past. Skipping MPOWR payment settlement.")
                        supabase.table("reservations").update({"mpwr_payment_settled": True}).eq("tw_confirmation", tw_conf).execute()
                        mark_webhook_status(supabase, wh_id, "processed")
                        continue
                except Exception as e:
                    pass

            log.info(f"[{tw_conf}] Balance is $0. Attempting MPOWR settlement.")
            
            # The amount to settle is typically the payload's "amount" field, or we just let MPOWR auto-fill
            # payload["amount"] is in cents.
            charge_amount = float(payload.get("amount", 0)) / 100.0

            success = process_settlement(mpwr_id, tw_conf, charge_amount)
            if success:
                try:
                    supabase.table("reservations").update({"mpwr_payment_settled": True}).eq("tw_confirmation", tw_conf).execute()
                    
                    # DOME V4 Audit Trail
                    from core.supabase_client import log_audit
                    log_audit(
                        agent_id="mpwr_payment",
                        action_type="payment_settled",
                        summary=f"Settled payment of ${charge_amount:.2f} for {tw_conf} in MPOWR #{mpwr_id}",
                        details={"tw_conf": tw_conf, "mpowr_id": mpwr_id, "amount": charge_amount}
                    )
                except Exception as e:
                    log.error(f"[{tw_conf}] DB Error setting settled flag or audit: {e}")
                mark_webhook_status(supabase, wh_id, "processed")
            else:
                # Failed to settle, retry later
                mark_webhook_status(supabase, wh_id, "retry")
        else:
            if mpwr_payment_settled:
                log.info(f"[{tw_conf}] Payment already settled in MPOWR. Ignoring.")
            else:
                log.info(f"[{tw_conf}] Balance not zero (Due: ${amount_due:.2f}). No MPOWR action needed.")
            mark_webhook_status(supabase, wh_id, "processed")

def mark_webhook_status(supabase, wh_id: str, status: str):
    try:
        supabase.table("pending_payment_webhooks").update({
            "status": status,
            "processed_at": datetime.now(timezone.utc).isoformat() if status == "processed" else None
        }).eq("id", wh_id).execute()
    except Exception as e:
        log.error(f"Failed to update webhook {wh_id} status to {status}: {e}")

if __name__ == "__main__":
    process_payment_webhooks()
