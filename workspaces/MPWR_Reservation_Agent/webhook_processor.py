import os
import re
import json
import hashlib
from dotenv import load_dotenv
from supabase import create_client
from mpowr_creator_bot import MpowrCreatorBot
from slack_notifier import slack
from bot_logger import get_bot_logger

load_dotenv()
log = get_bot_logger()

# Sentinel values that should NEVER be written to the mpwr_number column
_INVALID_MPWR_IDS = {"UNKNOWN", "EXISTS", "ERROR", "DRY_RUN", "EXTRACTION_FAILED", ""}

def _is_valid_mpwr_id(mpwr_id: str) -> bool:
    """Returns True if the MPOWR ID looks like a real confirmation code (e.g., CO-Y86-RQP)."""
    if not mpwr_id or mpwr_id.strip().upper() in _INVALID_MPWR_IDS:
        return False
    return bool(re.match(r'^[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+$', mpwr_id.strip(), re.IGNORECASE))


def _create_bot():
    """Instantiate MpowrCreatorBot with credentials from .env, matching main.py."""
    email = os.getenv("MPOWR_EMAIL")
    pwd = os.getenv("MPOWR_PASSWORD")
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    headless = os.getenv("CREATOR_HEADLESS", "true").lower() == "true"
    return MpowrCreatorBot(email=email, password=pwd, headless=headless, dry_run=dry_run)

def process_webhooks():
    log.debug("[WebhookProcessor] Polling Supabase for pending webhooks...")
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        log.error("[WebhookProcessor] Missing SUPABASE_URL or SUPABASE_KEY in .env")
        return
        
    try:
        supabase = create_client(url, key)
        res = supabase.table("pending_webhooks").select("*").in_("status", ["pending", "retry"]).order("created_at", desc=False).execute()
        records = res.data
    except Exception as e:
        log.error(f"[WebhookProcessor] Supabase connection failed: {e}")
        return
        
    if not records:
        return

    created_this_batch = {}
    bot = None
    dashboard_records = None
    
    def _mark_webhook(record_id, status):
        try:
            updates = {"status": status}
            if status == "processed":
                updates["processed_at"] = "now()"
            supabase.table("pending_webhooks").update(updates).eq("id", record_id).execute()
        except Exception as e:
            log.error(f"Failed to update webhook {record_id} to {status}: {e}")
            
    def _flush_other_webhooks_for_conf(tw_conf_code):
        try:
            supabase.table("pending_webhooks").update({"status": "processed", "processed_at": "now()"}).eq("tw_confirmation", tw_conf_code).in_("status", ["pending", "retry"]).execute()
        except Exception as e:
            log.error(f"Failed to flush pending webhooks for {tw_conf_code}: {e}")
            
    for row in records:
        row_id = row.get("id")
        fname = f"webhook_{row_id}"
        try:
            payload = row.get("payload", {})
            data = {"_payload": payload, "_headers": row.get("headers", {})}
            
            payload_hash = row.get("payload_hash", "")
                
            # Determine TW Conf
            tw_conf = payload.get("confirmation_code")
            if not tw_conf and "trip" in payload:
                trip_dict = payload["trip"] if isinstance(payload["trip"], dict) else {}
                tw_conf = trip_dict.get("confirmation_code")
            
            if not tw_conf:
                log.warning(f"  -> Skipping {fname}: No TW Confirmation Code found.")
                _mark_webhook(row_id, "processed")
                continue
                
            # Skip Gift Cards and Addon-only purchases
            if not payload.get("tripOrders"):
                log.info(f"  -> Skipping {fname} ({tw_conf}): No tripOrders found (likely a Gift Card).")
                _mark_webhook(row_id, "processed")
                continue
                
            # Early Identify Event Type for Race Condition Protection
            is_cancel = False
            
            # NOTE: Payment auto-settle is DISABLED. Epic 4x4 settles in cash with MPOWR
            # and never puts customer card info into the system. All TripWorks "payment"
            # webhooks are effectively just booking confirmations with due=0.
            # The dashboard Amount Due field is updated via update_dashboard_row when needed.
            
            if "tripOrders" in payload and len(payload["tripOrders"]) > 0:
                first_order = payload["tripOrders"][0] if isinstance(payload["tripOrders"][0], dict) else {}
                status_dict = first_order.get("status") or {}
                slug = status_dict.get("slug", "")
                if slug == "cancelled":
                    is_cancel = True
            
            # Fetch Dashboard DB exactly once per batch to locate the MPWR IDs
            if dashboard_records is None:
                try:
                    # Query Supabase instead of Google Sheets
                    res = supabase.table("reservations").select("tw_confirmation, mpwr_number").execute()
                    dashboard_records = res.data or []
                except Exception as e:
                    log.error(f"[WebhookProcessor] Could not connect to Dashboard DB: {e}")
                    return # Stop batch safely if DB is unreachable
                    
            # Check if this TW Confirm already exists in the Dashboard
            mpwr_id = None
            for row in dashboard_records:
                if str(row.get("tw_confirmation", "")).strip().upper() == tw_conf.upper():
                    raw_mpwr = row.get("mpwr_number")
                    mpwr_id = str(raw_mpwr) if raw_mpwr else None
                    break
            
            if not mpwr_id:
                # FIX-1: Check in-batch tracking first (handles same-cycle duplicates)
                if tw_conf.upper() in created_this_batch:
                    mpwr_id = created_this_batch[tw_conf.upper()]
                    log.info(f"  -> Found MPWR ID '{mpwr_id}' for {tw_conf} in current batch cache. Routing to UPDATE.")
                
            if not mpwr_id:
                # Legacy fallback lookups removed as part of V2 Supabase migration
                pass
            if not mpwr_id:
                if is_cancel:
                    # Can't cancel what doesn't exist yet — park for retry
                    
                    log.info(f"  -> Moving {fname} to retry: Waiting on MPWR ID for Cancel.")
                    _mark_webhook(row_id, "retry")
                    continue
                else:
                    # ============================================================
                    # WEBHOOK-FIRST CREATION: New booking — create directly from
                    # webhook data instead of waiting for Zapier Sheet
                    # ============================================================
                    slug = ""
                    if "tripOrders" in payload and len(payload["tripOrders"]) > 0:
                        first_order = payload["tripOrders"][0] if isinstance(payload["tripOrders"][0], dict) else {}
                        status_dict = first_order.get("status") or {}
                        slug = status_dict.get("slug", "")
                    
                    if slug == "booked":
                        # FIX-1: Final dedup guard — check in-batch tracking one more time
                        if tw_conf.upper() in created_this_batch:
                            existing_id = created_this_batch[tw_conf.upper()]
                            log.info(f"  -> DEDUP GUARD: {tw_conf} already created this batch as {existing_id}. Skipping duplicate creation.")
                            _mark_webhook(row_id, "processed")
                            
                            continue
                        
                        log.info(f"  -> NEW BOOKING detected for {tw_conf}. Using webhook-first creation...")
                        
                        from shared.tripworks_mapper import build_payloads_from_webhook
                        from shared.tripworks_mapper import map_legacy_to_dashboard
                        from pricing import split_subtotal
                        
                        # Build payloads from clean webhook data (supports mixed bookings)
                        creation_payloads = build_payloads_from_webhook(data)
                        
                        valid_payloads = []
                        for p in creation_payloads:
                            if p.get("error"):
                                error_msg = p["error"]
                                log.info(f"  -> {tw_conf} webhook creation skipped: {error_msg}")
                                if error_msg.startswith("Skipped:"):
                                    slack.send_message(
                                        f"⏭️ *[INTENTIONAL SKIP]* {tw_conf}\n"
                                        f"*Customer:* {payload.get('display_name', 'Unknown')}\n"
                                        f"*Reason:* {error_msg}"
                                    )
                                else:
                                    slack.send_message(
                                        f"⚠️ *[WEBHOOK CREATION FAILED]* {tw_conf}\n"
                                        f"*Customer:* {payload.get('display_name', 'Unknown')}\n"
                                        f"*Error:* {error_msg}"
                                    )
                            else:
                                valid_payloads.append(p)
                                
                        if not valid_payloads:
                            _mark_webhook(row_id, "processed")
                            continue
                            
                        # Sum each payload's per-order target_price for the split base
                        # Each target_price is already correctly calculated per-tripOrder by the mapper
                        adjusted_subtotal_dollars = sum(p.get("target_price", 0.0) for p in valid_payloads)
                        valid_payloads = split_subtotal(valid_payloads, adjusted_subtotal_dollars)

                        # Create the reservations
                        if not bot:
                            bot = _create_bot()
                        
                        results = bot.create_batch(valid_payloads)
                        
                        success_mpwr_ids = []
                        for res in results:
                            if res and res.status == "success" and res.mpowr_conf_id:
                                success_mpwr_ids.append(res.mpowr_conf_id)
                            elif res and res.status == "duplicate":
                                if res.mpowr_conf_id and _is_valid_mpwr_id(res.mpowr_conf_id):
                                    success_mpwr_ids.append(res.mpowr_conf_id)
                                else:
                                    log.warning(f"  -> Duplicate detected for {tw_conf} but no valid MPOWR ID extracted.")
                            else:
                                error_msg = res.error_message if res else "Bot returned no result"
                                log.error(f"  -> Webhook-first creation FAILED for {tw_conf}: {error_msg}")
                        
                        if success_mpwr_ids:
                            # Join multiple IDs (e.g. mixed bookings) for the dashboard
                            mpwr_conf_joined = ", ".join(success_mpwr_ids)
                            log.info(f"  -> ✅ Webhook-first creation SUCCESS for {tw_conf}: {mpwr_conf_joined}")
                            
                            # Track in batch immediately to prevent same-cycle doubles
                            created_this_batch[tw_conf.upper()] = mpwr_conf_joined
                            
                            # DOME V4 Audit Trail (Fire-and-forget)
                            primary_p = valid_payloads[0]
                            try:
                                from core.supabase_client import log_audit
                                log_audit(
                                    agent_id="mpwr_creator",
                                    action_type="reservation_created",
                                    summary=f"Created {tw_conf} → MPOWR #{mpwr_conf_joined}",
                                    details={"tw_conf": tw_conf, "mpowr_id": mpwr_conf_joined, "activity": primary_p.get("activity", "")}
                                )
                            except Exception as e:
                                log.warning(f"Failed to log DOME audit trail: {e}")
                            
                            # Push to Dashboard DB (Supabase)
                            try:
                                log.info(f"[Dashboard] Attempting DB push for {tw_conf}...")
                                # Build a minimal row dict for map_legacy_to_dashboard (using first payload for base metadata)
                                row_for_dash = {
                                    "TW Confirmation": tw_conf,
                                    "First Name": primary_p["first_name"],
                                    "Last Name": primary_p["last_name"],
                                    "Email": (payload.get("customer") or {}).get("email", ""),
                                    "Phone": primary_p["phone"],
                                    "Activity": primary_p["activity"] + (" (+More)" if len(valid_payloads) > 1 else ""),
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
                                    mpwr_conf_number=mpwr_conf_joined,
                                    webhook_payload=payload,
                                )
                                
                                # FIX: map_legacy_to_dashboard re-runs _build_single_payload with
                                # an empty Ticket Type, which causes it to error out and hit the
                                # BUG-4 fallback (blanking mpowr_vehicle, mpowr_activity).
                                # Override with the correct values from primary_p, which was already
                                # computed from the full webhook payload via build_payloads_from_webhook.
                                if primary_p.get("mpowr_vehicle"):
                                    dashboard_row["Vehicle Model"] = primary_p["mpowr_vehicle"]
                                if primary_p.get("mpowr_activity"):
                                    dashboard_row["Activity Internal"] = primary_p["mpowr_activity"]
                                if primary_p.get("vehicle_qty"):
                                    dashboard_row["Vehicle Qty"] = primary_p["vehicle_qty"]
                                
                                # Explicit mapping from Dashboard keys to Supabase columns
                                _DASH_TO_SUPABASE = {
                                    "TW Confirmation": "tw_confirmation",
                                    "TW Order ID": "tw_order_id",
                                    "First Name": None,  # Combined into guest_name below
                                    "Last Name": None,   # Combined into guest_name below
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
                                    "Normalized Date": None, # Column doesn't exist in Supabase
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
                                    "MPWR Status": None, # Column doesn't exist in Supabase
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
                                    "TW Customer Portal URL": "tw_customer_portal_url",
                                    "Trip Method": "trip_method",
                                    "Notes": "notes",
                                    "Created At": "created_at",
                                    "Last Updated": "last_updated",
                                }
                                
                                snake_row = {}
                                for k, v in dashboard_row.items():
                                    sb_col = _DASH_TO_SUPABASE.get(k)
                                    if sb_col is None:
                                        continue  # Skip unmapped keys (First Name, Last Name)
                                    # Type coercion for boolean columns
                                    if sb_col in ("ohv_required", "ohv_uploaded", "checked_in"):
                                        snake_row[sb_col] = str(v).strip().upper() == "TRUE"
                                    # Type coercion for integer columns
                                    elif sb_col in ("epic_expected", "epic_complete", "polaris_expected", "polaris_complete",
                                                     "ohv_expected", "ohv_complete", "party_size", "vehicle_qty"):
                                        try:
                                            snake_row[sb_col] = int(v) if v else 0
                                        except (ValueError, TypeError):
                                            snake_row[sb_col] = 0
                                    # Type coercion for float columns
                                    elif sb_col in ("sub_total", "total", "amount_paid", "amount_due"):
                                        try:
                                            snake_row[sb_col] = float(str(v).replace("$", "").replace(",", "")) if v else 0.0
                                        except (ValueError, TypeError):
                                            snake_row[sb_col] = 0.0
                                    # Array columns
                                    elif sb_col in ("epic_names", "polaris_names", "ohv_permit_names"):
                                        snake_row[sb_col] = [x.strip() for x in str(v).split(",")] if v else []
                                    # Timestamp columns — None if empty
                                    elif sb_col in ("created_at", "last_updated", "checked_in_at"):
                                        snake_row[sb_col] = str(v) if v else None
                                    else:
                                        snake_row[sb_col] = str(v) if v is not None else ""
                                
                                # Normalize activity_date from MM/DD/YYYY to YYYY-MM-DD
                                # to match the Updater's expected format and prevent false deltas
                                for date_col in ("activity_date", "end_date"):
                                    if date_col in snake_row and "/" in str(snake_row[date_col]):
                                        try:
                                            from datetime import datetime as _dt
                                            snake_row[date_col] = _dt.strptime(snake_row[date_col], "%m/%d/%Y").strftime("%Y-%m-%d")
                                        except (ValueError, TypeError):
                                            pass
                                
                                # Build guest_name from First + Last
                                first = str(dashboard_row.get("First Name", "")).strip()
                                last = str(dashboard_row.get("Last Name", "")).strip()
                                snake_row["guest_name"] = f"{first} {last}".strip()
                                
                                # Extract TripWorks booking IDs for status-changed webhook matching
                                booking_ids = []
                                for to in payload.get("tripOrders", []):
                                    to_dict = to if isinstance(to, dict) else {}
                                    for b in to_dict.get("bookings", []):
                                        b_dict = b if isinstance(b, dict) else {}
                                        bid = b_dict.get("id")
                                        if bid and isinstance(bid, int):
                                            booking_ids.append(bid)
                                if booking_ids:
                                    snake_row["tw_booking_ids"] = booking_ids
                                
                                # Validation gate: never write junk MPOWR IDs to the database
                                if _is_valid_mpwr_id(mpwr_conf_joined):
                                    snake_row["mpwr_number"] = mpwr_conf_joined
                                else:
                                    log.error(f"[Dashboard] Invalid MPOWR ID '{mpwr_conf_joined}' for {tw_conf}. Omitting from DB push.")
                                    snake_row.pop("mpwr_number", None)
                                        
                                supabase.table("reservations").upsert(snake_row).execute()
                                log.info(f"[Dashboard] ✅ Successfully pushed {tw_conf} to Guest Database v2")
                                
                                # Generate QR code for TripWorks customer portal (Epic waiver completion)
                                tw_portal_url = snake_row.get("tw_customer_portal_url", "")
                                if tw_portal_url:
                                    try:
                                        import qrcode
                                        import io
                                        qr = qrcode.make(tw_portal_url)
                                        buffer = io.BytesIO()
                                        qr.save(buffer, format="PNG")
                                        buffer.seek(0)
                                        
                                        # Upload to Supabase Storage
                                        qr_file_path = f"portal_{tw_conf}.png"
                                        try:
                                            supabase.storage.from_("waiver-qr-codes").remove([qr_file_path])
                                        except Exception:
                                            pass
                                        supabase.storage.from_("waiver-qr-codes").upload(
                                            path=qr_file_path,
                                            file=buffer.getvalue(),
                                            file_options={"content-type": "image/png", "upsert": "true"},
                                        )
                                        qr_public_url = supabase.storage.from_("waiver-qr-codes").get_public_url(qr_file_path)
                                        
                                        # Update the reservation with the QR code URL
                                        supabase.table("reservations").update({
                                            "tw_customer_portal_qr_url": qr_public_url,
                                        }).eq("tw_confirmation", tw_conf.upper()).execute()
                                        log.info(f"[QR] ✅ Generated customer portal QR for {tw_conf}")
                                    except ImportError:
                                        log.warning(f"[QR] qrcode library not installed. Skipping QR generation for {tw_conf}.")
                                    except Exception as qr_err:
                                        log.warning(f"[QR] Failed to generate portal QR for {tw_conf}: {qr_err}")
                                
                                # Update in-memory cache
                                if dashboard_records is not None:
                                    dashboard_records.append({
                                        "tw_confirmation": tw_conf,
                                        "mpwr_number": mpwr_conf_joined,
                                    })
                            except Exception as db_err:
                                log.error(f"[Dashboard] Failed to push {tw_conf}: {db_err}")
                            
                            # Flush all other webhook files for this TW Confirmation
                            _flush_other_webhooks_for_conf(tw_conf)
                        
                        # Only mark as processed if at least one creation succeeded
                        if success_mpwr_ids:
                            _mark_webhook(row_id, "processed")
                        else:
                            log.warning(f"  -> ALL creations failed for {tw_conf}. Setting to retry.")
                            _mark_webhook(row_id, "retry")
                        continue
                    else:
                        # Non-booked webhook for unknown ID — park for retry
                        
                        log.info(f"  -> Moving {fname} to retry: Waiting on MPWR ID (status: {slug}).")
                        _mark_webhook(row_id, "retry")
                        continue
                
            # ============================================================
            # UPDATE / CANCEL: Handled by the dedicated MPWR_Update_Cancel_Agent.
            # This agent only creates new reservations. If we reach here, it means
            # a webhook for an existing reservation was routed to this agent.
            # Mark it as processed — the Update/Cancel Agent will pick it up
            # from its own cancel_webhooks / update_webhooks tables.
            # ============================================================
            log.info(f"  -> Existing reservation {tw_conf} (MPWR: {mpwr_id}). Updates/Cancels handled by dedicated agent. Marking processed.")
            
                
            _mark_webhook(row_id, "processed")
            
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            log.error(f"Error processing webhook {fname}: {e}\n{tb_str}")
            slack.send_message(f"⚠️ [WEBHOOK PROCESSING ERROR] Critical parsing error while processing `{fname}`. Reason: {e}")
            
    if bot:
        try:
            bot._close_browser()
        except Exception:
            pass
