"""
webhook_processor.py — Processes Cancel and Update Queues
"""
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client
from mpowr_updater_bot import MpowrUpdaterBot
from slack_notifier import slack
from bot_logger import get_bot_logger

load_dotenv()
log = get_bot_logger()

# Maximum time a webhook stays in 'retry' before being marked 'failed'
RETRY_TTL = timedelta(hours=24)

def _is_retry_expired(row) -> bool:
    """Check if a retry webhook has exceeded its TTL based on created_at."""
    created_str = row.get("created_at", "")
    if not created_str:
        return False
    try:
        created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - created_at > RETRY_TTL
    except (ValueError, TypeError):
        return False

# Maintain a single bot instance per polling cycle to avoid browser overhead
_bot_instance = None

def _get_bot():
    global _bot_instance
    if _bot_instance is None:
        email = os.getenv("MPOWR_EMAIL")
        pwd = os.getenv("MPOWR_PASSWORD")
        dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        headless = os.getenv("CREATOR_HEADLESS", "true").lower() == "true"
        _bot_instance = MpowrUpdaterBot(email=email, password=pwd, headless=headless, dry_run=dry_run)
    return _bot_instance

def _close_bot():
    global _bot_instance
    if _bot_instance:
        try:
            _bot_instance._close_browser()
        except Exception:
            pass
        _bot_instance = None

def _get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)

def _mark_webhook(supabase, table_name, row, status):
    record_id = row.get("id")
    try:
        updates = {"status": status}
        if status == "processed":
            updates["processed_at"] = datetime.now(timezone.utc).isoformat()
        if status == "retry":
            current_retries = row.get("retry_count", 0)
            updates["retry_count"] = current_retries + 1
        supabase.table(table_name).update(updates).eq("id", record_id).execute()
    except Exception as e:
        log.error(f"Failed to update {table_name} {record_id} to {status}: {e}")

def process_webhooks():
    supabase = _get_supabase()
    if not supabase:
        log.error("[WebhookProcessor] Missing Supabase credentials")
        return

    # Process CANCELLATIONS
    try:
        res = supabase.table("cancel_webhooks").select("*").in_("status", ["pending", "retry"]).order("created_at", desc=False).execute()
        cancels = res.data or []
    except Exception as e:
        log.error(f"[WebhookProcessor] Failed to fetch cancel_webhooks: {e}")
        cancels = []

    processed_cancels = set()
    for row in cancels:
        payload = row.get("payload", {})
        tw_conf = payload.get("confirmation_code")
        if not tw_conf and "trip" in payload:
            tw_conf = payload["trip"].get("confirmation_code")
            
        if tw_conf and tw_conf in processed_cancels:
            log.info(f"  [Cancel] Skipping duplicate webhook for {tw_conf} in this batch.")
            _mark_webhook(supabase, "cancel_webhooks", row, "processed")
            continue
            
        _process_cancel(supabase, row)
        if tw_conf:
            processed_cancels.add(tw_conf)

    # Process UPDATES
    try:
        res = supabase.table("update_webhooks").select("*").in_("status", ["pending", "retry"]).order("created_at", desc=False).execute()
        updates = res.data or []
    except Exception as e:
        log.error(f"[WebhookProcessor] Failed to fetch update_webhooks: {e}")
        updates = []

    processed_updates = set()
    for row in updates:
        payload = row.get("payload", {})
        tw_conf = payload.get("confirmation_code")
        if not tw_conf and "trip" in payload:
            tw_conf = payload["trip"].get("confirmation_code")
            
        if tw_conf and tw_conf in processed_updates:
            log.info(f"  [Update] Skipping duplicate webhook for {tw_conf} in this batch.")
            _mark_webhook(supabase, "update_webhooks", row, "processed")
            continue
            
        _process_update(supabase, row)
        if tw_conf:
            processed_updates.add(tw_conf)

    # Always clean up browser session at the end of the batch
    _close_bot()


def _process_cancel(supabase, row):
    row_id = row.get("id")
    payload = row.get("payload", {})
    
    tw_conf = payload.get("confirmation_code")
    if not tw_conf and "trip" in payload:
        tw_conf = payload["trip"].get("confirmation_code")

    if not tw_conf:
        log.warning(f"  [Cancel] Skipping {row_id}: No TW Confirmation Code found.")
        _mark_webhook(supabase, "cancel_webhooks", row, "processed")
        return

    # Skip Gift Cards and Addon-only purchases
    if not payload.get("tripOrders"):
        log.info(f"  [Cancel] Skipping {row_id} ({tw_conf}): No tripOrders found (likely a Gift Card).")
        _mark_webhook(supabase, "cancel_webhooks", row, "processed")
        return

    log.info(f"[Cancel] Processing cancellation for {tw_conf}")

    # Lookup MPWR ID from Supabase reservations table
    try:
        res = supabase.table("reservations").select("mpwr_number, activity_date").eq("tw_confirmation", tw_conf.upper()).execute()
        if not res.data:
            if _is_retry_expired(row):
                log.warning(f"  [Cancel] Reservation {tw_conf} not found after 1hr TTL. Marking as failed.")
                slack.send_message(f"🚨 [ORPHANED WEBHOOK] Cancellation webhook for {tw_conf} expired after 1-hour TTL. Could not find a matching database record.")
                _mark_webhook(supabase, "cancel_webhooks", row, "failed")
            else:
                log.warning(f"  [Cancel] Reservation {tw_conf} not found in Supabase yet. Marking as retry.")
                _mark_webhook(supabase, "cancel_webhooks", row, "retry")
            return
        existing_row = res.data[0]
        mpwr_number = existing_row.get("mpwr_number")
        activity_date_str = existing_row.get("activity_date")
    except Exception as e:
        log.error(f"  [Cancel] Failed to query reservations for {tw_conf}: {e}")
        return

    if not mpwr_number or mpwr_number in ("0", "0.0", "", "NOT_REQUIRED"):
        log.info(f"  [Cancel] No MPWR number for {tw_conf}. Just deleting from Supabase.")
        # We can just delete the row
        _delete_reservation(supabase, tw_conf)
        _mark_webhook(supabase, "cancel_webhooks", row, "processed")
        return

    # Skip MPOWR automation for reservations in the past
    if activity_date_str:
        try:
            from datetime import datetime
            import pytz
            act_date = datetime.strptime(activity_date_str, "%Y-%m-%d").date()
            today = datetime.now(pytz.timezone('America/Denver')).date()
            if act_date < today:
                log.info(f"  [Cancel] Activity date {act_date} is in the past. Just deleting from Supabase.")
                _delete_reservation(supabase, tw_conf)
                _mark_webhook(supabase, "cancel_webhooks", row, "processed")
                return
        except Exception:
            pass

    # Cancel in MPOWR first
    bot = _get_bot()
    success = bot.cancel_reservation(mpwr_number)

    if success:
        log.info(f"  ✅ [Cancel] Successfully canceled {mpwr_number} in MPOWR.")
        slack.send_message(f"⏭️ [INTENTIONAL OPERATION] Cancelled MPOWR booking {mpwr_number} to match TripWorks refund for {tw_conf}.")
        
        # DOME V4 Audit Trail
        try:
            from core.supabase_client import log_audit
            log_audit(
                agent_id="mpwr_updater",
                action_type="reservation_cancelled",
                summary=f"Cancelled {tw_conf} in MPOWR #{mpwr_number}",
                details={"tw_conf": tw_conf, "mpowr_id": mpwr_number}
            )
        except Exception as e:
            log.warning(f"Failed to log DOME audit trail: {e}")
            
        # Now delete from Supabase to keep data pure
        _delete_reservation(supabase, tw_conf)
        _mark_webhook(supabase, "cancel_webhooks", row, "processed")
    else:
        log.error(f"  ❌ [Cancel] Failed to cancel {mpwr_number} in MPOWR.")
        slack.send_message(f"🚨 [MPOWR CANCEL FAILURE] TripWorks successfully unbooked {tw_conf}, but MPOWR integration failed to cancel {mpwr_number}. Please manually cancel to prevent locking inventory.")
        # Mark as failed or retry? Let's leave it as pending/retry or mark processed so we don't loop endlessly?
        # A failed UI interaction usually means a hard failure or edge case (like it was already canceled)
        _mark_webhook(supabase, "cancel_webhooks", row, "failed")


def _delete_reservation(supabase, tw_conf):
    try:
        supabase.table("reservations").delete().eq("tw_confirmation", tw_conf.upper()).execute()
        log.info(f"  🗑️ [Cancel] Deleted {tw_conf} from Supabase reservations table.")
    except Exception as e:
        log.error(f"  ❌ [Cancel] Failed to delete {tw_conf} from Supabase: {e}")


def _process_update(supabase, row):
    from shared.tripworks_mapper import extract_update_data

    row_id = row.get("id")
    payload = row.get("payload", {})
    
    tw_conf = payload.get("confirmation_code")
    if not tw_conf and "trip" in payload:
        tw_conf = payload["trip"].get("confirmation_code")

    if not tw_conf:
        log.warning(f"  [Update] Skipping {row_id}: No TW Confirmation Code found.")
        _mark_webhook(supabase, "update_webhooks", row, "processed")
        return

    # Skip Gift Cards and Addon-only purchases
    if not payload.get("tripOrders"):
        log.info(f"  [Update] Skipping {row_id} ({tw_conf}): No tripOrders found (likely a Gift Card).")
        _mark_webhook(supabase, "update_webhooks", row, "processed")
        return

    log.info(f"[Update] Processing update for {tw_conf}")

    # Map webhook data to a clean dictionary using data_mapper
    try:
        update_data = extract_update_data(payload)
    except Exception as e:
        log.error(f"  [Update] Failed to extract data from webhook payload for {tw_conf}: {e}")
        _mark_webhook(supabase, "update_webhooks", row, "failed")
        return

    if update_data.get("error"):
        log.warning(f"  [Update] Mapping error for {tw_conf}: {update_data['error']}")
        _mark_webhook(supabase, "update_webhooks", row, "processed")
        return

    # Lookup existing reservation in Supabase
    try:
        res = supabase.table("reservations").select("*").eq("tw_confirmation", tw_conf.upper()).execute()
        existing_row = res.data[0] if res.data else None
    except Exception as e:
        log.error(f"  [Update] Failed to query reservations for {tw_conf}: {e}")
        return

    if not existing_row:
        if _is_retry_expired(row):
            log.warning(f"  [Update] Reservation {tw_conf} not found after 1hr TTL. Marking as failed.")
            slack.send_message(f"🚨 [ORPHANED WEBHOOK] Update webhook for {tw_conf} expired after 1-hour TTL. Could not find a matching database record.")
            _mark_webhook(supabase, "update_webhooks", row, "failed")
        else:
            log.warning(f"  [Update] Reservation {tw_conf} not found in Supabase yet. Marking as retry.")
            _mark_webhook(supabase, "update_webhooks", row, "retry")
        return

    mpwr_number = existing_row.get("mpwr_number")
    
    if not mpwr_number or mpwr_number in ("0", "0.0", "", "NOT_REQUIRED"):
        log.info(f"  [Update] No MPWR number for {tw_conf}. Skipping MPOWR update.")
        _mark_webhook(supabase, "update_webhooks", row, "processed")
        return

    # -- DATE CHECK --
    # Skip MPOWR automation for reservations in the past
    db_updates = update_data["supabase_updates"]
    activity_date_str = db_updates.get("activity_date") or existing_row.get("activity_date")
    if activity_date_str:
        try:
            from datetime import datetime
            import pytz
            act_date = datetime.strptime(activity_date_str, "%Y-%m-%d").date()
            today = datetime.now(pytz.timezone('America/Denver')).date()
            if act_date < today:
                log.info(f"  [Date] Activity date {act_date} is in the past. Skipping MPOWR update.")
                try:
                    supabase.table("reservations").update(db_updates).eq("tw_confirmation", tw_conf.upper()).execute()
                    log.info(f"  ✅ [Update] Updated Supabase for {tw_conf} (Historical Update).")
                except Exception as e:
                    log.error(f"  ❌ [Update] Failed to update Supabase for {tw_conf}: {e}")
                _mark_webhook(supabase, "update_webhooks", row, "processed")
                return
        except Exception as e:
            log.warning(f"  [Date] Could not parse activity date {activity_date_str}: {e}")

    # -- DELTA DETECTION --
    core_fields = ["activity_name", "activity_date", "activity_time", "vehicle_model", "vehicle_qty"]
    core_changed = False
    
    for field in core_fields:
        old_val = str(existing_row.get(field, "")).strip().lower()
        new_val = str(db_updates.get(field, "")).strip().lower()
        if old_val != new_val:
            core_changed = True
            log_old = old_val if old_val else "missing"
            log.info(f"  [Delta] Core field '{field}' changed: '{log_old}' -> '{new_val}'")
            break

    if not core_changed:
        log.info(f"  [Delta] No core MPOWR fields changed for {tw_conf}. Skipping Playwright UI automation.")
        try:
            supabase.table("reservations").update(db_updates).eq("tw_confirmation", tw_conf.upper()).execute()
            log.info(f"  ✅ [Update] Updated Supabase minor fields for {tw_conf}.")
        except Exception as e:
            log.error(f"  ❌ [Update] Failed to update Supabase minor fields for {tw_conf}: {e}")
        _mark_webhook(supabase, "update_webhooks", row, "processed")
        return

    # 1. Update MPOWR using the extracted bot payload
    bot_payload = update_data["mpowr_payload"]
    bot = _get_bot()
    
    # Check if there's multiple MPWR IDs (e.g. mixed bookings). For now, assume 1-to-1 or split update logic.
    mpwr_ids = [i.strip() for i in mpwr_number.split(",") if i.strip()]
    all_success = True

    for current_id in mpwr_ids:
        log.info(f"  -> Updating MPOWR {current_id} for {tw_conf}...")
        success = bot.update_reservation(current_id, bot_payload)
        if not success:
            all_success = False
            log.error(f"  ❌ [Update] Failed to update MPOWR reservation {current_id}.")
            customer_name = bot_payload.get("customer_name", "Unknown")
            slack.send_error_alert(
                customer_name=customer_name,
                activity_date=bot_payload.get("activity_date", "Unknown"),
                activity=bot_payload.get("activity", "Unknown"),
                vehicle_type=bot_payload.get("mpowr_vehicle", "Unknown"),
                error_reason=f"MPOWR bot attempted to reschedule but failed. Manual update required.\\nMPWR ID: {current_id}",
                tw_confirmation=tw_conf,
            )

    # 2. Update Supabase with incoming data REGARDLESS of MPOWR success,
    # because TripWorks is the source of truth for operations
    db_updates = update_data["supabase_updates"]
    try:
        supabase.table("reservations").update(db_updates).eq("tw_confirmation", tw_conf.upper()).execute()
        log.info(f"  ✅ [Update] Updated Supabase row for {tw_conf} with source of truth data.")
    except Exception as e:
        log.error(f"  ❌ [Update] Failed to update Supabase for {tw_conf}: {e}")

    if all_success:
        log.info(f"  ✅ [Update] Successfully updated MPOWR for {tw_conf}.")
        slack.send_message(f"✅ [SYSTEM AUTOMATION] Successfully updated/rescheduled {tw_conf} (MPWR {mpwr_number}) based on TripWorks changes.")
        
        # DOME V4 Audit Trail
        try:
            from core.supabase_client import log_audit
            log_audit(
                agent_id="mpwr_updater",
                action_type="reservation_updated",
                summary=f"Updated {tw_conf} in MPOWR #{mpwr_number}",
                details={"tw_conf": tw_conf, "mpowr_id": mpwr_number}
            )
        except Exception as e:
            log.warning(f"Failed to log DOME audit trail: {e}")
            
        _mark_webhook(supabase, "update_webhooks", row, "processed")
    else:
        _mark_webhook(supabase, "update_webhooks", row, "failed")
