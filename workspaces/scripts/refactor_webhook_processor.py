import os
import re

file_path = r"c:\DOME_CORE\workspaces\MPWR_Reservation_Agent\webhook_processor.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# We need to extract the dashboard_row and snake_row logic from lines 244-404
# and move it to a helper function at the top level or just above `def _process_webhooks`.
# But actually, an easier way is to just define a helper in the file.

helper_code = """
def _generate_and_upload_qr(supabase, tw_conf, tw_portal_url):
    try:
        import qrcode
        import io
        import logging
        log = logging.getLogger("MPWR_Creator_Agent")
        qr = qrcode.make(tw_portal_url)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        buffer.seek(0)
        
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
        
        supabase.table("reservations").update({
            "tw_customer_portal_qr_url": qr_public_url,
        }).eq("tw_confirmation", tw_conf.upper()).execute()
        log.info(f"[QR] ✅ Generated customer portal QR for {tw_conf} (Async)")
    except Exception as qr_err:
        logging.getLogger("MPWR_Creator_Agent").warning(f"[QR] Failed to generate portal QR for {tw_conf}: {qr_err}")

def _build_supabase_row(tw_conf, payload, valid_payloads, adjusted_subtotal_dollars, mpwr_conf_joined=None):
    from shared.tripworks_mapper import map_legacy_to_dashboard
    primary_p = valid_payloads[0]
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
        mpwr_conf_number=mpwr_conf_joined if mpwr_conf_joined else "",
        webhook_payload=payload,
    )
    
    if primary_p.get("mpowr_vehicle"):
        dashboard_row["Vehicle Model"] = primary_p["mpowr_vehicle"]
    if primary_p.get("mpowr_activity"):
        dashboard_row["Activity Internal"] = primary_p["mpowr_activity"]
    if primary_p.get("vehicle_qty"):
        dashboard_row["Vehicle Qty"] = primary_p["vehicle_qty"]
    
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
    
    for date_col in ("activity_date", "end_date"):
        if date_col in snake_row and "/" in str(snake_row[date_col]):
            try:
                from datetime import datetime as _dt
                snake_row[date_col] = _dt.strptime(snake_row[date_col], "%m/%d/%Y").strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
    
    first = str(dashboard_row.get("First Name", "")).strip()
    last = str(dashboard_row.get("Last Name", "")).strip()
    snake_row["guest_name"] = f"{first} {last}".strip()
    
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
    
    if mpwr_conf_joined:
        from mpowr_creator_bot import _is_valid_mpwr_id
        if _is_valid_mpwr_id(mpwr_conf_joined):
            snake_row["mpwr_number"] = mpwr_conf_joined
        else:
            snake_row.pop("mpwr_number", None)
            
    return snake_row
"""

if "def _build_supabase_row" not in content:
    content = content.replace("def _process_webhooks(", helper_code + "\n\ndef _process_webhooks(")

# Now replace the inline mapping with the helper call
old_bot_create_start = """                        # Create the reservations
                        if not bot:"""

new_bot_create_start = """                        # TWO-PHASE COMMIT: Insert pending row before bot execution
                        snake_row = _build_supabase_row(tw_conf, payload, valid_payloads, adjusted_subtotal_dollars)
                        snake_row["mpwr_number"] = None
                        
                        try:
                            supabase.table("reservations").upsert(snake_row).execute()
                            log.info(f"[Dashboard] ✅ Inserted pending row for {tw_conf} before bot execution")
                        except Exception as e:
                            log.error(f"[Dashboard] ❌ Failed to insert pending row for {tw_conf}: {e}")

                        # Create the reservations
                        if not bot:"""

content = content.replace(old_bot_create_start, new_bot_create_start)

# Now remove lines 244 to 441 and replace with the update logic

match = re.search(r'# Push to Dashboard DB \(Supabase\).*?# Update in-memory cache', content, re.DOTALL)
if match:
    old_push_logic = match.group(0)
    
    new_push_logic = """# Update the pending Supabase row
                            try:
                                supabase.table("reservations").update({
                                    "mpwr_number": mpwr_conf_joined,
                                }).eq("tw_confirmation", tw_conf.upper()).execute()
                                log.info(f"[Dashboard] ✅ Successfully updated {tw_conf} with MPOWR ID")
                                
                                # Async QR generation
                                tw_portal_url = snake_row.get("tw_customer_portal_url", "")
                                if tw_portal_url:
                                    import threading
                                    threading.Thread(target=_generate_and_upload_qr, args=(supabase, tw_conf, tw_portal_url)).start()
                                    
                            except Exception as db_err:
                                log.error(f"[Dashboard] Failed to update {tw_conf} with MPOWR ID: {db_err}")

                            # Update in-memory cache"""
                            
    content = content.replace(old_push_logic, new_push_logic)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done.")
