"""
main.py — Epic 4x4 Dashboard API Server

Serves three surfaces:
  1. Staff Operations Dashboard  → /staff, /api/arrivals
  2. TV Arrival Board            → /tv, /api/tv/rentals, /api/tv/tours
  3. Customer Portal             → /portal/:code, /api/portal/:code

Also handles:
  - TripWorks waiver completion webhooks
  - OHV permit uploads
  - Staff actions (check-in, payment, notes)
"""

import os
import re
import json
import time
import asyncio
import hashlib
import hmac
import threading
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

import pytz
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from passlib.context import CryptContext
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
# APScheduler removed — using asyncio background task instead

from api_models import (
    ArrivalGuest, ArrivalBoardResponse, TVBoardResponse,
    CustomerPortalResponse, OHVUploadResponse,
    CheckInRequest, CollectPaymentRequest, UpdateNotesRequest,
    WaiverProgress,
)
from supabase_data import (
    fetch_todays_arrivals, fetch_by_tw_conf,
    update_field, update_multiple_fields, increment_waiver_count,
    fetch_all_records, _parse_date, fetch_upcoming_reservations,
)
from ohv_storage import save_ohv_permit, ohv_exists
from supabase_client import get_supabase

load_dotenv()

MDT = pytz.timezone("America/Denver")
PUBLIC_DOMAIN = os.getenv("PUBLIC_DOMAIN", "epicreservation.com")

# Authentication Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    print("[SECURITY WARNING] JWT_SECRET not set! Generating a temporary one. Set it in .env for production.")
    import secrets as _secrets
    JWT_SECRET = _secrets.token_urlsafe(48)

# Webhook authentication key (shared with TripWorks configuration)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# Login rate limiter: {ip: (attempt_count, first_attempt_time)}
_login_attempts: dict[str, tuple[int, float]] = {}
LOGIN_RATE_LIMIT = 5        # max attempts
LOGIN_RATE_WINDOW = 300     # per 5 minutes (seconds)

# Refresh rate limiter: {ip: last_refresh_time}
_refresh_timestamps: dict[str, float] = {}
REFRESH_COOLDOWN = 2       # minimum seconds between refreshes per IP

# In-memory cache for fast dashboard reads
_arrival_cache: ArrivalBoardResponse | None = None
_cache_timestamp: datetime | None = None
CACHE_TTL_SECONDS = 15  # 15s for near-real-time waiver updates (safe with Supabase)
_cache_lock = threading.Lock()

# Reference to the main asyncio event loop (set during startup)
_main_loop: asyncio.AbstractEventLoop | None = None

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()


# =============================================================================
# HELPERS
# =============================================================================

def get_client_ip(request: Request) -> str:
    """Extract true client IP, prioritizing X-Forwarded-For if behind a proxy like Railway."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def safe_float(val, default=0.0) -> float:
    """Safely parse a string/number to float, handling currency and text."""
    try:
        if not val:
            return default
        cleaned = str(val).replace("$", "").replace(",", "").strip()
        if not cleaned:
            return default
        return float(cleaned)
    except ValueError:
        return default


def safe_int(val, default=0) -> int:
    """Safely parse a string/number to int, stripping non-numeric text."""
    try:
        if not val:
            return default
        cleaned = re.sub(r'[^\d\-]', '', str(val))
        if not cleaned:
            return default
        return int(cleaned)
    except ValueError:
        return default


def _normalize_time(time_str: str) -> str:
    """Normalize a time value into a clean 'H:MM AM/PM' format.
    Handles:
      - Excel serial fractions: 0.333333 → '8:00 AM'
      - Seconds in times: '9:00:00 AM' → '9:00 AM'
      - Already-clean times: '5:00 PM' → '5:00 PM' (passthrough)
    """
    if not time_str:
        return ""
    time_str = str(time_str).strip()
    if not time_str:
        return ""

    # Handle Excel serial fraction (e.g. 0.333333 = 8:00 AM, 0.375 = 9:00 AM)
    try:
        val = float(time_str)
        if 0 < val < 1:
            total_minutes = round(val * 24 * 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            period = "AM" if hours < 12 else "PM"
            display_hour = hours % 12
            if display_hour == 0:
                display_hour = 12
            return f"{display_hour}:{minutes:02d} {period}"
    except ValueError:
        pass

    # Strip seconds from times like '9:00:00 AM' → '9:00 AM'
    cleaned = re.sub(r'(\d{1,2}:\d{2}):\d{2}(\s*[APap][Mm])', r'\1\2', time_str)
    # Also handle 24h format with seconds like '09:00:00' → '09:00'
    cleaned = re.sub(r'^(\d{1,2}:\d{2}):\d{2}$', r'\1', cleaned)

    return cleaned


def _parse_time(time_str: str) -> datetime | None:
    """Parse a time string like '8:00 AM' into a datetime for today."""
    if not time_str:
        return None

    # Normalize first (handles Excel decimals, strips seconds)
    time_str = _normalize_time(time_str)
    if not time_str:
        return None
    time_str = re.sub(r'(\d)(am|pm)', r'\1 \2', time_str, flags=re.IGNORECASE)
    time_str = time_str.upper().strip()

    # Bare hour: '8 AM' → '8:00 AM'
    match = re.match(r'^(\d{1,2})\s*(AM|PM)$', time_str)
    if match:
        time_str = f"{match.group(1)}:00 {match.group(2)}"

    for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M"]:
        try:
            parsed = datetime.strptime(time_str, fmt)
            now = datetime.now(MDT)
            return now.replace(
                hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0,
            )
        except ValueError:
            continue
    return None


def _compute_deposit_status(row: dict) -> str:
    """
    Compute deposit status from financial fields.
    Premier AA ≠ Waived. Waived only when balance explicitly compensated.
    Returns 'N/A' for tours with no financial data rather than misleading 'Due'.
    """
    amount_due = safe_float(row.get("amount_due"))
    amount_paid = safe_float(row.get("amount_paid"))
    manual_status = str(row.get("deposit_status", "") or "").strip()

    # Manual override from staff
    if manual_status.lower() in ("collected", "compensated"):
        return manual_status.capitalize()

    if amount_due <= 0 and amount_paid > 0:
        return "Collected"
    elif amount_due > 0:
        return "Due"
    else:
        # Both zero: for tours this often means no deposit is required
        booking_type = str(row.get("booking_type", "")).strip().lower()
        if booking_type == "tour":
            return "N/A"
        return "Due"


def _row_to_arrival_guest(row: dict, now: datetime = None) -> ArrivalGuest:
    if now is None:
        now = datetime.now(MDT)
    tw_conf = str(row.get("tw_confirmation", "")).strip()
    guest_name = str(row.get("guest_name", "")).strip()
    booking_type_raw = str(row.get("booking_type", "")).strip()
    # Normalize to title case and infer for empty records
    if booking_type_raw:
        booking_type = booking_type_raw.capitalize()  # "tour" → "Tour", "rental" → "Rental"
    else:
        # Infer from activity_name for records with empty booking_type
        act = str(row.get("activity_name", "")).lower()
        if any(t in act for t in ["hell's", "poison spider", "discovery", "pro xperience", "tripadvisor", "gateway"]):
            booking_type = "Tour"
        elif any(t in act for t in ["rental", "hour", "day", "self-guided", "rzr", "pro s", "pro r", "xp s", "ultimate"]):
            booking_type = "Rental"
        else:
            booking_type = "Tour"  # Default: most bookings are tours
    is_rental = booking_type.lower() == "rental"

    epic_complete = safe_int(row.get("epic_complete"))
    epic_names = row.get("epic_names") or []

    pol_complete = safe_int(row.get("polaris_complete"))
    pol_names = row.get("polaris_names") or []

    # Dynamic Expected Logic
    party_size = max(1, safe_int(row.get("party_size", 1)))
    pol_expected = party_size
    
    if is_rental:
        epic_expected = max(1, safe_int(row.get("vehicle_qty", 1)))
    else:
        epic_expected = party_size

    ohv_required = is_rental
    ohv_uploaded = bool(row.get("ohv_uploaded"))
    if not ohv_uploaded:
        ohv_uploaded = ohv_exists(tw_conf)
    ohv_expected = safe_int(row.get("ohv_expected"))
    ohv_complete = safe_int(row.get("ohv_complete"))
    ohv_permit_names = row.get("ohv_permit_names") or []

    deposit_status = _compute_deposit_status(row)
    checked_in = bool(row.get("checked_in"))

    mpwr_id_raw = str(row.get("mpwr_number", "") or "").strip()
    mpwr_id = mpwr_id_raw if mpwr_id_raw and mpwr_id_raw not in ("0", "0.0") else ""
    primary_rider = str(row.get("primary_rider", "") or "").strip()
    rental_return_time = _normalize_time(str(row.get("rental_return_time", "") or ""))
    rental_status = str(row.get("rental_status", "") or "").strip()

    # TripWorks status (from status-changed webhook)
    tw_status = str(row.get("tw_status", "") or "").strip()
    # Auto-derive rental_status from tw_status if not already set
    if is_rental and tw_status == "Rental Out" and not rental_status:
        rental_status = "On Ride"
    if tw_status == "Rental Returned" and rental_status != "OVERDUE":
        rental_status = "Returned"

    if is_rental and checked_in and rental_return_time and rental_status.lower() not in ("returned", "completed"):
        parsed_return = _parse_time(rental_return_time)
        if parsed_return and now > parsed_return:
            rental_status = "OVERDUE"
            
    adventure_assure = str(row.get("adventure_assure", "None") or "None")

    epic_ok = epic_complete >= epic_expected if epic_expected > 0 else True
    pol_ok = pol_complete >= pol_expected if pol_expected > 0 else True
    ohv_ok = ohv_uploaded if ohv_required else True
    dep_ok = deposit_status.lower() in ("collected", "compensated")
    overall = "ready" if (epic_ok and pol_ok and ohv_ok and dep_ok) else "not_ready"

    amount_due = safe_float(row.get("amount_due"))
    amount_paid = safe_float(row.get("amount_paid"))

    customer_portal = str(row.get("customer_portal_link", "") or "")
    if "ngrok.io" in customer_portal or "localhost" in customer_portal or not customer_portal:
        if tw_conf:
            customer_portal = f"https://www.{PUBLIC_DOMAIN}/portal/{tw_conf}"

    return ArrivalGuest(
        tw_confirmation=tw_conf,
        tw_order_id=str(row.get("tw_order_id", "") or ""),
        guest_name=guest_name,
        booking_type=booking_type,
        activity_name=str(row.get("activity_name", "") or ""),
        vehicle_model=str(row.get("vehicle_model", "") or ""),
        vehicle_qty=safe_int(row.get("vehicle_qty"), default=1),
        party_size=safe_int(row.get("party_size"), default=1),
        activity_time=_normalize_time(str(row.get("activity_time", "") or "")),
        activity_date=str(row.get("activity_date", "") or ""),
        overall_status=overall if not checked_in else "ready",
        epic_waivers=WaiverProgress(completed=epic_complete, expected=epic_expected, names=epic_names),
        polaris_waivers=WaiverProgress(completed=pol_complete, expected=pol_expected, names=pol_names),
        ohv_required=ohv_required,
        ohv_uploaded=ohv_uploaded,
        ohv_expected=ohv_expected,
        ohv_complete=ohv_complete,
        ohv_permit_names=ohv_permit_names,
        deposit_status=deposit_status,
        amount_due=amount_due,
        amount_paid=amount_paid,
        adventure_assure=adventure_assure,
        checked_in=checked_in,
        checked_in_at=str(row.get("checked_in_at", "") or "") or None,
        rental_return_time=rental_return_time,
        rental_status=rental_status,
        primary_rider=primary_rider or guest_name,
        tw_link=str(row.get("tw_link", "") or ""),
        mpwr_link=f"https://mpwr-hq.poladv.com/orders/{mpwr_id}" if mpwr_id else "",
        mpwr_number=mpwr_id,
        mpwr_waiver_link=str(row.get("mpwr_waiver_link", "") or ""),
        mpwr_waiver_qr_url=str(row.get("mpwr_waiver_qr_url", "") or ""),
        customer_portal_link=customer_portal,
        notes=str(row.get("notes", "") or ""),
        trip_method=str(row.get("trip_method", "") or ""),
        trip_safe=str(row.get("trip_safe", "") or ""),
        tw_status=tw_status,
    )


# TripWorks statuses that trigger ON RIDE / RETURNED placement
_ON_RIDE_STATUSES = {"Checked In", "Rental Out", "No Show"}
_RETURNED_STATUSES = {"Rental Returned"}


def _bucket_arrivals(guests: list[ArrivalGuest]) -> ArrivalBoardResponse:
    """Split guests into now/next (<=30 min), upcoming (>30 min), and checked-in.
    Uses both the internal checked_in flag and tw_status for bucketing."""
    now = datetime.now(MDT)
    now_next = []
    upcoming = []
    checked = []

    for guest in guests:
        # ON RIDE: checked_in flag OR TripWorks status indicates on ride
        if guest.checked_in or guest.tw_status in _ON_RIDE_STATUSES or guest.tw_status in _RETURNED_STATUSES:
            checked.append(guest)
            continue

        guest_time = _parse_time(guest.activity_time)
        if not guest_time:
            upcoming.append(guest)
            continue

        diff_minutes = (guest_time - now).total_seconds() / 60

        if diff_minutes <= 30:
            now_next.append(guest)
        else:
            upcoming.append(guest)

    # Sort each bucket chronologically by date AND time
    def sort_key(g):
        t_str = g.activity_time or ""
        d_str = getattr(g, "activity_date", None) or now.strftime("%Y-%m-%d")
        
        # Parse time and date together
        t = _parse_time(t_str)
        if t:
            try:
                dt = datetime.strptime(f"{d_str} {t.strftime('%H:%M')}", "%Y-%m-%d %H:%M").replace(tzinfo=MDT)
                return dt
            except:
                pass
        return datetime.max.replace(tzinfo=MDT)

    now_next.sort(key=sort_key)
    upcoming.sort(key=sort_key)

    return ArrivalBoardResponse(
        now_next=now_next,
        upcoming=upcoming,
        checked_in=checked,
        last_refresh=now.strftime("%I:%M %p"),
        active_count=len(now_next) + len(upcoming),
        total_today=len(guests),
    )


def _refresh_cache_sync():
    """Synchronous cache refresh — called from asyncio via run_in_executor.
    No locks, no threads, no deadlocks.
    Merges today's arrivals with future reservations to always fill UPCOMING with 30 items."""
    global _arrival_cache, _cache_timestamp
    now = datetime.now(MDT)
    rows = fetch_todays_arrivals()
    guests = [_row_to_arrival_guest(r, now=now) for r in rows]
    bucketed = _bucket_arrivals(guests)

    # UPCOMING = next 90 reservations: fill from future days if today's upcoming < 90
    if len(bucketed.upcoming) < 90:
        try:
            future_rows = fetch_upcoming_reservations(limit=90)
            existing_confs = {g.tw_confirmation for g in
                bucketed.now_next + bucketed.upcoming + bucketed.checked_in}
            for row in future_rows:
                tc = row.get("tw_confirmation", "")
                if tc and tc not in existing_confs:
                    guest = _row_to_arrival_guest(row, now=now)
                    # Skip on-ride / returned guests from future days
                    if guest.tw_status not in _ON_RIDE_STATUSES and guest.tw_status not in _RETURNED_STATUSES and not guest.checked_in:
                        bucketed.upcoming.append(guest)
                        existing_confs.add(tc)
                if len(bucketed.upcoming) >= 90:
                    break
        except Exception as e:
            print(f"[Cache] Error fetching upcoming reservations: {e}")

    _arrival_cache = bucketed
    _cache_timestamp = datetime.now(MDT)
    return bucketed


async def _refresh_cache_async():
    """Async cache refresh — runs the blocking Supabase call in an executor
    then broadcasts to WebSockets. Safe, simple, no threading issues."""
    try:
        loop = asyncio.get_running_loop()
        bucketed = await asyncio.wait_for(
            loop.run_in_executor(None, _refresh_cache_sync),
            timeout=30
        )
        print(f"[Cache] Refreshed: {bucketed.total_today} arrivals today")
        await manager.broadcast({
            "type": "update",
            "arrivals": bucketed.model_dump()
        })
    except asyncio.TimeoutError:
        print("[Cache] Refresh timed out after 30s — will retry next cycle")
    except Exception as e:
        print(f"[Cache] Refresh failed: {e}")


async def _periodic_cache_refresh():
    """Background asyncio task that refreshes the cache every 60 seconds.
    Replaces APScheduler — runs on the event loop, no thread-safety issues."""
    while True:
        await asyncio.sleep(60)
        await _refresh_cache_async()


def _get_cached_arrivals() -> ArrivalBoardResponse:
    """Get arrivals from cache. If cache is stale, returns stale data
    (the background task will refresh it shortly)."""
    if _arrival_cache is not None:
        return _arrival_cache
    # First request before cache is primed — do a synchronous fetch
    try:
        _refresh_cache_sync()
    except Exception as e:
        print(f"[Cache] Initial fetch failed: {e}")
    return _arrival_cache or ArrivalBoardResponse()


# =============================================================================
# APP LIFECYCLE
# =============================================================================

_refresh_task = None  # Reference to the background refresh task


def _cleanup_webhook_cache(max_age_days: int = 7):
    """Remove webhook cache files older than max_age_days to prevent unbounded growth."""
    cache_dirs = [
        os.path.join(os.path.dirname(__file__), "webhook_cache"),
        os.path.join(os.path.dirname(__file__), "status_webhook_cache"),
        os.path.join(os.path.dirname(__file__), "payment_webhook_cache"),
    ]
    cutoff = datetime.now().timestamp() - (max_age_days * 86400)
    removed = 0
    for cache_dir in cache_dirs:
        if not os.path.exists(cache_dir):
            continue
        for fname in os.listdir(cache_dir):
            fpath = os.path.join(cache_dir, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                try:
                    os.remove(fpath)
                    removed += 1
                except OSError:
                    pass
    if removed:
        print(f"[Startup] Cleaned up {removed} old webhook cache file(s).")


def _enrich_reservation_from_payload(tw_conf: str, payload: dict):
    """
    Opportunistic data enrichment: extracts any available data from a TripWorks
    webhook payload and fills in empty/missing columns in the reservations table.
    
    This is called by EVERY webhook endpoint (new booking, update, cancel, payment,
    status) to progressively build complete records — especially valuable for
    legacy data that was imported without full TripWorks fields.
    
    RULE: Only updates columns that are currently empty/null/default.
    Never overwrites existing populated data.
    """
    if not tw_conf:
        return
    
    try:
        supabase = get_supabase()
        existing = supabase.table("reservations") \
            .select("*") \
            .eq("tw_confirmation", tw_conf.upper()) \
            .execute()
        
        if not existing.data:
            return  # Reservation doesn't exist yet — MPWR agent will create it
        
        row = existing.data[0]
        updates = {}
        
        # --- Navigate to trip data (payment webhooks nest under "trip") ---
        trip = payload.get("trip", payload)  # Payment webhook has trip.*, others have it at top level
        customer = trip.get("customer", {})
        trip_orders = trip.get("tripOrders", [])
        
        # --- Basic customer info ---
        if not row.get("email") and customer.get("email"):
            updates["email"] = customer["email"]
        
        if not row.get("phone"):
            phone = customer.get("phone_format_intl") or customer.get("phone") or ""
            if phone:
                updates["phone"] = phone
        
        if not row.get("guest_name") and customer.get("full_name"):
            updates["guest_name"] = customer["full_name"]
        
        # --- Order-level data ---
        if not row.get("tw_order_id") and trip.get("id"):
            updates["tw_order_id"] = str(trip["id"])
        
        if not row.get("trip_method") and trip.get("trip_method", {}).get("name"):
            updates["trip_method"] = trip["trip_method"]["name"]
        
        # --- Financial data (always update to latest — TripWorks is source of truth) ---
        if "subtotal" in trip:
            new_subtotal = trip["subtotal"] / 100.0
            if not row.get("sub_total") or float(row.get("sub_total", 0)) == 0:
                updates["sub_total"] = new_subtotal
        
        if "total" in trip:
            new_total = trip["total"] / 100.0
            if not row.get("total") or float(row.get("total", 0)) == 0:
                updates["total"] = new_total
        
        if "paid" in trip:
            updates["amount_paid"] = trip["paid"] / 100.0
        
        if "due" in trip:
            updates["amount_due"] = trip["due"] / 100.0
            # Update deposit status based on balance
            if trip["due"] == 0:
                updates["deposit_status"] = "Collected"
            elif trip["due"] > 0 and row.get("deposit_status") != "Compensated":
                updates["deposit_status"] = "Due"
        
        # --- Booking IDs (critical for status webhook matching) ---
        current_booking_ids = row.get("tw_booking_ids") or []
        new_booking_ids = []
        for to in trip_orders:
            for b in to.get("bookings", []):
                bid = b.get("id")
                if bid and isinstance(bid, int) and bid not in current_booking_ids:
                    new_booking_ids.append(bid)
        if new_booking_ids:
            updates["tw_booking_ids"] = list(set(current_booking_ids + new_booking_ids))
        
        # --- TripWorks link (always ensure it's correct) ---
        expected_link = f"https://epic4x4.tripworks.com/trip/{tw_conf.upper()}/bookings"
        if not row.get("tw_link") or row.get("tw_link") != expected_link:
            updates["tw_link"] = expected_link
        
        # --- Customer portal link ---
        portal = f"https://www.epicreservation.com/portal/{tw_conf.upper()}"
        if not row.get("customer_portal_link") or "ngrok" in str(row.get("customer_portal_link", "")) or "localhost" in str(row.get("customer_portal_link", "")):
            updates["customer_portal_link"] = portal
        
        # --- Experience / activity data ---
        if trip_orders:
            to = trip_orders[0]
            exp = to.get("experience", {})
            ts = to.get("experience_timeslot", {})
            
            if not row.get("activity_name") and exp.get("name"):
                updates["activity_name"] = exp["name"]
            
            # Extract end_time for rental returns
            if not row.get("rental_return_time") and ts.get("end_time"):
                updates["rental_return_time"] = _normalize_time(ts["end_time"])
            
            if not row.get("party_size") or int(row.get("party_size", 0)) == 0:
                pax = to.get("pax_count")
                if pax and pax > 0:
                    updates["party_size"] = pax
        
        # --- Notes (from custom fields) ---
        if not row.get("notes"):
            for cf in trip.get("custom_field_values", []):
                cf_name = str(cf.get("custom_field", {}).get("internal_name", "")).lower()
                if "notes" in cf_name or "internal" in cf_name:
                    val = cf.get("string_value") or cf.get("text_value") or ""
                    if val and val.strip():
                        updates["notes"] = val.strip()
                        break
        
        # --- Timestamp ---
        if updates:
            updates["last_updated"] = datetime.now(MDT).isoformat()
            update_multiple_fields(tw_conf.upper(), updates)
            enriched_fields = [k for k in updates.keys() if k != "last_updated"]
            print(f"[Enrich] {tw_conf}: filled {len(enriched_fields)} field(s): {', '.join(enriched_fields)}")
    
    except Exception as e:
        print(f"[Enrich] Error enriching {tw_conf}: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    global _main_loop, _refresh_task
    _main_loop = asyncio.get_running_loop()

    # Prime cache on startup (synchronous, on main thread — always works)
    try:
        _refresh_cache_sync()
        print(f"[Startup] Cache primed: {_arrival_cache.total_today if _arrival_cache else 0} arrivals today")
    except Exception as e:
        print(f"[Startup] Cache prime failed (expected if Supabase not configured): {e}")

    # Start background asyncio task for periodic refresh (replaces APScheduler)
    _refresh_task = asyncio.create_task(_periodic_cache_refresh())

    # Cleanup old webhook cache files (older than 7 days)
    _cleanup_webhook_cache()

    print("[Startup] Dashboard server ready. Cache refresh every 60s.")

    yield

    # Cancel the background task on shutdown
    if _refresh_task:
        _refresh_task.cancel()
    _main_loop = None
    print("[Shutdown] Dashboard server stopped.")


app = FastAPI(title="Epic 4x4 Operations Dashboard", lifespan=lifespan)

# CORS configuration
VERCEL_PREVIEW_DOMAIN = os.getenv("VERCEL_PREVIEW_DOMAIN", "epic-waiver-dashboard.vercel.app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://localhost:3000",
        # Custom domain
        f"https://{PUBLIC_DOMAIN}",
        f"https://www.{PUBLIC_DOMAIN}",
        f"http://{PUBLIC_DOMAIN}",
        f"http://www.{PUBLIC_DOMAIN}",
        # Vercel preview/production domains
        f"https://{VERCEL_PREVIEW_DOMAIN}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


@app.post("/api/login")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    # Rate limiting by true client IP
    client_ip = get_client_ip(request)
    now_ts = time.time()
    attempts, first_ts = _login_attempts.get(client_ip, (0, now_ts))
    if now_ts - first_ts > LOGIN_RATE_WINDOW:
        attempts, first_ts = 0, now_ts
    if attempts >= LOGIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again in a few minutes.")
    _login_attempts[client_ip] = (attempts + 1, first_ts)

    try:
        supabase = get_supabase()
        res = supabase.table("staff_users").select("*").eq("username", form_data.username).execute()
        if not res.data:
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        
        user = res.data[0]
        if not pwd_context.verify(form_data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        
        # Success — clear rate limit for this IP
        _login_attempts.pop(client_ip, None)
            
        token = jwt.encode({
            "sub": user["username"],
            "exp": datetime.now(timezone.utc) + timedelta(days=7)
        }, JWT_SECRET, algorithm="HS256")
        
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# STAFF DASHBOARD ENDPOINTS
# =============================================================================

@app.websocket("/api/ws/arrivals")
async def websocket_arrivals(websocket: WebSocket):
    """Real-time WebSocket endpoint for the staff dashboard.
    Includes a 30-second ping heartbeat to prevent Railway idle timeout."""
    await manager.connect(websocket)
    try:
        # Send initial state immediately upon connection
        cache = _get_cached_arrivals()
        await websocket.send_json({
            "type": "init",
            "arrivals": cache.model_dump()
        })
        while True:
            # Wait for client messages with a 30s timeout for heartbeat
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)


@app.get("/api/arrivals", response_model=ArrivalBoardResponse)
def get_arrivals():
    """Staff dashboard: today's arrivals bucketed by time window."""
    return _get_cached_arrivals()


@app.get("/api/resolve-confirmation")
def resolve_confirmation(q: str = ""):
    """Resolve a TW confirmation code or MPWR number to a TW confirmation.
    Used by the guest kiosk search screen."""
    q = q.strip().upper()
    if not q:
        return JSONResponse({"error": "No query provided"}, status_code=400)
    
    try:
        supabase = get_supabase()
        
        # Try TW confirmation first
        res = supabase.table("reservations").select("tw_confirmation").eq("tw_confirmation", q).limit(1).execute()
        if res.data:
            return {"tw_confirmation": res.data[0]["tw_confirmation"]}
        
        # Try MPWR number
        res = supabase.table("reservations").select("tw_confirmation").eq("mpwr_number", q).limit(1).execute()
        if res.data:
            return {"tw_confirmation": res.data[0]["tw_confirmation"]}
        
        return JSONResponse({"error": "Reservation not found"}, status_code=404)
    except Exception as e:
        print(f"[API] Error resolving confirmation: {e}")
        return JSONResponse({"error": "Server error"}, status_code=500)


@app.post("/api/check-in/{tw_conf}")
def check_in(tw_conf: str, req: CheckInRequest, user: str = Depends(get_current_user)):
    """Mark a reservation as checked in."""
    now = datetime.now(MDT).strftime("%I:%M %p")
    success = update_multiple_fields(tw_conf, {
        "checked_in": True,
        "checked_in_at": now,
        "checked_in_by": req.staff_name,
    })
    if not success:
        raise HTTPException(404, f"Reservation {tw_conf} not found")

    _refresh_cache_sync()
    return {"message": f"Checked in at {now}", "tw_confirmation": tw_conf}


@app.post("/api/collect-payment/{tw_conf}")
def collect_payment(tw_conf: str, req: CollectPaymentRequest, user: str = Depends(get_current_user)):
    """Mark a deposit as collected."""
    success = update_multiple_fields(tw_conf, {
        "deposit_status": "Collected",
        "payment_notes": req.notes,
    })
    if not success:
        raise HTTPException(404, f"Reservation {tw_conf} not found")

    _refresh_cache_sync()
    return {"message": "Payment collected", "tw_confirmation": tw_conf}


@app.patch("/api/notes/{tw_conf}")
def update_notes(tw_conf: str, req: UpdateNotesRequest, user: str = Depends(get_current_user)):
    """Update operational notes for a reservation."""
    success = update_field(tw_conf, "notes", req.notes)
    if not success:
        raise HTTPException(404, f"Reservation {tw_conf} not found")

    _refresh_cache_sync()
    return {"message": "Notes updated", "tw_confirmation": tw_conf}


# =============================================================================
# TV BOARD ENDPOINTS
# =============================================================================

@app.get("/api/tv/rentals", response_model=TVBoardResponse)
def get_tv_rentals():
    """TV board: today's rental reservations only."""
    board = _get_cached_arrivals()
    return TVBoardResponse(
        now_next=[g for g in board.now_next if g.booking_type.lower() == "rental"],
        upcoming=[g for g in board.upcoming if g.booking_type.lower() == "rental"],
        last_refresh=board.last_refresh,
        filter_type="rental",
    )


@app.get("/api/tv/tours", response_model=TVBoardResponse)
def get_tv_tours():
    """TV board: today's tour reservations only."""
    board = _get_cached_arrivals()
    return TVBoardResponse(
        now_next=[g for g in board.now_next if g.booking_type.lower() == "tour"],
        upcoming=[g for g in board.upcoming if g.booking_type.lower() == "tour"],
        last_refresh=board.last_refresh,
        filter_type="tour",
    )


@app.get("/api/tv/all", response_model=TVBoardResponse)
def get_tv_all():
    """TV board: all reservations."""
    board = _get_cached_arrivals()
    return TVBoardResponse(
        now_next=board.now_next,
        upcoming=board.upcoming,
        last_refresh=board.last_refresh,
        filter_type="all",
    )


# =============================================================================
# CUSTOMER PORTAL ENDPOINTS
# =============================================================================

@app.get("/api/portal/{tw_conf}", response_model=CustomerPortalResponse)
def get_portal(tw_conf: str):
    """Customer portal: reservation status, waivers, countdown.
    Uses the in-memory cache first, then falls back to a direct
    Supabase fetch if the reservation is not in today's cache."""
    tw_conf_clean = tw_conf.strip().upper()

    # Try cached data first
    board = _get_cached_arrivals()
    cached_guest = None
    for g in (board.now_next + board.upcoming + board.checked_in):
        if g.tw_confirmation.upper() == tw_conf_clean:
            cached_guest = g
            break

    if cached_guest:
        # Build countdown from cached guest data
        countdown_iso = ""
        if cached_guest.activity_date and cached_guest.activity_time:
            target = _parse_time(cached_guest.activity_time)
            if target:
                parsed_date = _parse_date(cached_guest.activity_date)
                if parsed_date:
                    target = target.replace(
                        year=parsed_date.year,
                        month=parsed_date.month,
                        day=parsed_date.day,
                    )
                    countdown_iso = target.isoformat()

        return CustomerPortalResponse(
            guest_name=cached_guest.guest_name,
            activity_name=cached_guest.activity_name,
            booking_type=cached_guest.booking_type,
            activity_date=cached_guest.activity_date,
            activity_time=cached_guest.activity_time,
            countdown_target_iso=countdown_iso,
            epic_waivers=cached_guest.epic_waivers,
            polaris_waivers=cached_guest.polaris_waivers,
            epic_waiver_url=f"https://epic4x4.tripworks.com/trip/{tw_conf_clean}/bookings",
            polaris_waiver_url=cached_guest.mpwr_waiver_link or "",
            polaris_waiver_qr_url=cached_guest.mpwr_waiver_qr_url or "",
            ohv_required=cached_guest.ohv_required,
            ohv_uploaded=cached_guest.ohv_uploaded,
            vehicle_model=cached_guest.vehicle_model,
            party_size=cached_guest.party_size,
            rental_return_time=cached_guest.rental_return_time,
        )

    # Fallback: direct Supabase fetch (for reservations not in today's cache)
    row = fetch_by_tw_conf(tw_conf)
    if not row:
        raise HTTPException(404, "Reservation not found. Please check your confirmation code.")

    guest = _row_to_arrival_guest(row)

    countdown_iso = ""
    if guest.activity_date and guest.activity_time:
        target = _parse_time(guest.activity_time)
        if target:
            parsed_date = _parse_date(guest.activity_date)
            if parsed_date:
                target = target.replace(
                    year=parsed_date.year,
                    month=parsed_date.month,
                    day=parsed_date.day,
                )
                countdown_iso = target.isoformat()

    return CustomerPortalResponse(
        guest_name=guest.guest_name,
        activity_name=guest.activity_name,
        booking_type=guest.booking_type,
        activity_date=guest.activity_date,
        activity_time=guest.activity_time,
        countdown_target_iso=countdown_iso,
        epic_waivers=guest.epic_waivers,
        polaris_waivers=guest.polaris_waivers,
        epic_waiver_url=f"https://epic4x4.tripworks.com/trip/{tw_conf_clean}/bookings",
        polaris_waiver_url=guest.mpwr_waiver_link or "",
        polaris_waiver_qr_url=guest.mpwr_waiver_qr_url or "",
        ohv_required=guest.ohv_required,
        ohv_uploaded=guest.ohv_uploaded,
        vehicle_model=guest.vehicle_model,
        party_size=guest.party_size,
        rental_return_time=guest.rental_return_time,
    )


@app.post("/api/portal/{tw_conf}/ohv", response_model=OHVUploadResponse)
async def upload_ohv(tw_conf: str, file: UploadFile = File(...)):
    """Upload OHV permit from customer portal (file picker or camera capture)."""
    try:
        contents = await file.read()
        path = save_ohv_permit(tw_conf, contents, file.filename or "upload.jpg")

        # Update database
        update_multiple_fields(tw_conf, {
            "ohv_uploaded": True,
            "ohv_file_path": path,
        })

        _refresh_cache_sync()
        return OHVUploadResponse(success=True, message="OHV permit uploaded successfully!", file_path=path)

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {e}")


# =============================================================================
# WEBHOOK ENDPOINTS
# =============================================================================

def _verify_webhook(request: Request):
    """Verify webhook authentication via X-Webhook-Secret header.
    If WEBHOOK_SECRET is set, the header must match. If not set, all webhooks are accepted."""
    if not WEBHOOK_SECRET:
        return  # No secret configured — accept all (development mode)
    incoming = request.headers.get("X-Webhook-Secret", "")
    if not hmac.compare_digest(incoming, WEBHOOK_SECRET):
        raise HTTPException(403, "Invalid webhook secret")


@app.post("/api/webhook/tw-mpwr-event")
async def tw_mpwr_event(request: Request):
    """
    Ingestion gateway for TripWorks MPOWR reservation webhooks.
    Saves payload to Supabase queue for local agent to process asynchronously.
    """
    # NOTE: TripWorks does not support custom webhook headers, so auth is disabled.
    # Webhooks are still protected by SHA-256 payload deduplication.
    # _verify_webhook(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Bad Request: Expected JSON")

    headers_dict = dict(request.headers)
    
    tw_conf = body.get("confirmation_code")
    if not tw_conf and "trip" in body:
        tw_conf = body["trip"].get("confirmation_code")
        
    payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    try:
        supabase = get_supabase()
        supabase.table("pending_webhooks").insert({
            "tw_confirmation": tw_conf,
            "headers": headers_dict,
            "payload": body,
            "payload_hash": payload_hash,
            "status": "pending"
        }).execute()
        print(f"[Webhook Queue] Queued MPOWR event for {tw_conf or 'unknown'}")
    except Exception as e:
        print(f"[Webhook Queue] Failed to insert: {e}")
        raise HTTPException(500, "Database Error")

    # Opportunistic enrichment: fill in any missing columns from the payload data
    if tw_conf:
        try:
            _enrich_reservation_from_payload(tw_conf, body)
        except Exception as e:
            print(f"[Webhook Queue] Enrichment failed (non-fatal): {e}")

    return {"status": "queued"}


@app.post("/api/webhook/tw-mpwr-cancel")
async def tw_mpwr_cancel(request: Request):
    """
    Ingestion gateway for TripWorks Cancel webhooks.
    Saves payload to Supabase cancel_webhooks queue.
    """
    # NOTE: TripWorks does not support custom webhook headers, so auth is disabled.
    # Webhooks are still protected by SHA-256 payload deduplication.
    # _verify_webhook(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Bad Request: Expected JSON")

    headers_dict = dict(request.headers)
    
    tw_conf = body.get("confirmation_code")
    if not tw_conf and "trip" in body:
        tw_conf = body["trip"].get("confirmation_code")
        
    payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    try:
        supabase = get_supabase()
        supabase.table("cancel_webhooks").insert({
            "tw_confirmation": tw_conf,
            "headers": headers_dict,
            "payload": body,
            "payload_hash": payload_hash,
            "status": "pending"
        }).execute()
        print(f"[Webhook Queue] Queued Cancel event for {tw_conf or 'unknown'}")
    except Exception as e:
        print(f"[Webhook Queue] Failed to insert cancel: {e}")
        raise HTTPException(500, "Database Error")

    return {"status": "queued"}


@app.post("/api/webhook/tw-mpwr-update")
async def tw_mpwr_update(request: Request):
    """
    Ingestion gateway for TripWorks Update webhooks.
    Saves payload to Supabase update_webhooks queue.
    """
    # NOTE: TripWorks does not support custom webhook headers, so auth is disabled.
    # Webhooks are still protected by SHA-256 payload deduplication.
    # _verify_webhook(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Bad Request: Expected JSON")

    headers_dict = dict(request.headers)
    
    tw_conf = body.get("confirmation_code")
    if not tw_conf and "trip" in body:
        tw_conf = body["trip"].get("confirmation_code")
        
    payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    try:
        supabase = get_supabase()
        supabase.table("update_webhooks").insert({
            "tw_confirmation": tw_conf,
            "headers": headers_dict,
            "payload": body,
            "payload_hash": payload_hash,
            "status": "pending"
        }).execute()
        print(f"[Webhook Queue] Queued Update event for {tw_conf or 'unknown'}")
    except Exception as e:
        print(f"[Webhook Queue] Failed to insert update: {e}")
        raise HTTPException(500, "Database Error")

    # Opportunistic enrichment: fill in any missing columns from the update payload
    if tw_conf:
        try:
            _enrich_reservation_from_payload(tw_conf, body)
        except Exception as e:
            print(f"[Webhook Queue] Enrichment failed (non-fatal): {e}")

    return {"status": "queued"}

@app.post("/api/webhook/tw-waiver-complete")
async def tw_waiver_complete(request: Request):
    """
    Ingestion gateway for TripWorks specialized webhooks (Waivers, etc.).
    Saves payload to the isolated 'recon_webhooks' Supabase queue.
    """
    # NOTE: TripWorks does not support custom webhook headers, so auth is disabled.
    # Webhooks are still protected by SHA-256 payload deduplication.
    # _verify_webhook(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Bad Request: Expected JSON")

    headers_dict = dict(request.headers)
    
    # Try to extract TW confirmation or Order ID for tracking if possible
    tw_conf = ""
    if "bookings" in body and isinstance(body["bookings"], list) and len(body["bookings"]) > 0:
        tw_conf = str(body["bookings"][0].get("id", ""))
    elif "customer" in body and "bookings" in body["customer"] and isinstance(body["customer"]["bookings"], list) and len(body["customer"]["bookings"]) > 0:
        tw_conf = str(body["customer"]["bookings"][0].get("id", ""))

    try:
        supabase = get_supabase()
        supabase.table("recon_webhooks").insert({
            "tw_confirmation": tw_conf,
            "headers": headers_dict,
            "webhook_type": "waiver.completed",
            "payload": body,
            "status": "pending"
        }).execute()
        print(f"[Webhook Queue] Queued specialized event (waiver.completed) for {tw_conf or 'unknown'}")
    except Exception as e:
        print(f"[Webhook Queue] Failed to insert: {e}")
        raise HTTPException(500, "Database Error")

    return {"status": "queued"}


@app.post("/api/webhook/tw-status-changed")
async def tw_status_changed(request: Request):
    """
    Inline handler for TripWorks "Guest Booking Updated" webhooks.
    Extracts the new booking status and directly updates the reservations table,
    then triggers a real-time cache refresh + WebSocket broadcast.

    Payload structure (confirmed from TripWorks docs):
    {
      "id": 5201661,                // booking ID
      "status": {"id": 15, "name": "Checked In"},
      "customer": {"full_name": "Jim Smith", ...},
      "trip_order": {"experience": {...}, "experience_timeslot": {...}},
      ...
    }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Bad Request: Expected JSON")

    # 1. Save raw payload to dedicated cache directory
    try:
        cache_dir = os.path.join(os.path.dirname(__file__), "status_webhook_cache")
        os.makedirs(cache_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cache_path = os.path.join(cache_dir, f"status_{ts}.json")
        with open(cache_path, "w") as f:
            json.dump(body, f, indent=2)
    except Exception as e:
        print(f"[Status Webhook] Cache save failed: {e}")

    # 2. Extract fields from confirmed payload structure
    booking_id = body.get("id")
    status_obj = body.get("status", {})
    status_name = status_obj.get("name", "") if isinstance(status_obj, dict) else ""
    customer = body.get("customer", {})
    customer_name = customer.get("full_name", "") if isinstance(customer, dict) else ""

    # TEMPORARY DIAGNOSTIC: Log the payload to DB so we can see it
    try:
        get_supabase().table("pending_webhooks").insert({
            "tw_confirmation": f"LOG_STATUS_{booking_id}",
            "payload": body
        }).execute()
    except Exception:
        pass

    print(f"[Status Webhook] Received: booking_id={booking_id}, status='{status_name}', customer='{customer_name}'")

    if not booking_id or not status_name:
        print(f"[Status Webhook] Missing booking_id or status_name, skipping")
        return {"status": "skipped", "reason": "missing booking_id or status"}

    # 3. Extract activity date from webhook payload for better matching
    trip_order = body.get("trip_order", {})
    timeslot = trip_order.get("experience_timeslot", {})
    webhook_start = timeslot.get("start_time", "")
    customer_email = customer.get("email", "") if isinstance(customer, dict) else ""
    customer_first = customer.get("first_name", "") if isinstance(customer, dict) else ""
    customer_last = customer.get("last_name", "") if isinstance(customer, dict) else ""
    experience_name = trip_order.get("experience", {}).get("name", "")

    # Parse the activity date from the webhook (more reliable than "today")
    activity_date_iso = ""
    webhook_time_label = ""
    if webhook_start:
        try:
            import re as _re
            clean_dt = _re.sub(r'[+-]\d{2}:\d{2}$', '', webhook_start.replace('Z', ''))
            wh_dt = datetime.fromisoformat(clean_dt)
            activity_date_iso = wh_dt.date().isoformat()  # "2026-04-25"
            webhook_time_label = wh_dt.strftime("%I:%M %p").lstrip("0")  # "9:00 AM"
        except Exception:
            pass

    # Fallback to today if webhook doesn't have a timeslot
    if not activity_date_iso:
        activity_date_iso = datetime.now(MDT).date().isoformat()
    activity_date_us = datetime.strptime(activity_date_iso, "%Y-%m-%d").strftime("%m/%d/%Y")

    print(f"[Status Webhook] Matching: booking_id={booking_id}, name='{customer_name}', "
          f"email='{customer_email}', date={activity_date_iso}, time='{webhook_time_label}', "
          f"activity='{experience_name}'")

    # 4. Multi-layer matching cascade (most specific → broadest)
    supabase = get_supabase()
    matched_row = None

    # --- Layer 1: Booking ID direct match (fastest, most precise) ---
    try:
        res = supabase.table("reservations") \
            .select("tw_confirmation, booking_type, tw_status, tw_booking_ids") \
            .filter("tw_booking_ids", "cs", f"[{booking_id}]") \
            .execute()
        if res.data:
            matched_row = res.data[0]
            print(f"[Status Webhook] ✅ Layer 1 HIT: booking_id match -> {matched_row['tw_confirmation']}")
    except Exception as e:
        print(f"[Status Webhook] Layer 1 error: {e}")

    # --- Layer 2: Customer email + activity date ---
    if not matched_row and customer_email:
        try:
            res = supabase.table("reservations") \
                .select("tw_confirmation, booking_type, tw_status, tw_booking_ids") \
                .or_(f"activity_date.eq.{activity_date_iso},activity_date.eq.{activity_date_us}") \
                .eq("email", customer_email) \
                .execute()
            if res.data:
                matched_row = res.data[0]
                print(f"[Status Webhook] ✅ Layer 2 HIT: email match -> {matched_row['tw_confirmation']}")
        except Exception as e:
            print(f"[Status Webhook] Layer 2 error: {e}")

    # --- Layer 3: Guest name contains customer full name + activity date ---
    if not matched_row and customer_name:
        try:
            res = supabase.table("reservations") \
                .select("tw_confirmation, booking_type, tw_status, tw_booking_ids") \
                .or_(f"activity_date.eq.{activity_date_iso},activity_date.eq.{activity_date_us}") \
                .ilike("guest_name", f"%{customer_name.strip()}%") \
                .execute()
            if res.data:
                matched_row = res.data[0]
                print(f"[Status Webhook] ✅ Layer 3 HIT: full name match -> {matched_row['tw_confirmation']}")
        except Exception as e:
            print(f"[Status Webhook] Layer 3 error: {e}")

    # --- Layer 4: Customer last name + activity date (broader — catches family bookings) ---
    if not matched_row and customer_last and len(customer_last) >= 3:
        try:
            res = supabase.table("reservations") \
                .select("tw_confirmation, booking_type, tw_status, tw_booking_ids, guest_name") \
                .or_(f"activity_date.eq.{activity_date_iso},activity_date.eq.{activity_date_us}") \
                .ilike("guest_name", f"%{customer_last.strip()}%") \
                .execute()
            if res.data:
                # If multiple matches, prefer the one with matching first name
                best = None
                for r in res.data:
                    if customer_first.lower() in r.get("guest_name", "").lower():
                        best = r
                        break
                matched_row = best or res.data[0]
                print(f"[Status Webhook] ✅ Layer 4 HIT: last name match -> {matched_row['tw_confirmation']}")
        except Exception as e:
            print(f"[Status Webhook] Layer 4 error: {e}")

    # --- Layer 5: Email-only match (no date constraint — last resort for legacy data) ---
    if not matched_row and customer_email:
        try:
            res = supabase.table("reservations") \
                .select("tw_confirmation, booking_type, tw_status, tw_booking_ids") \
                .eq("email", customer_email) \
                .order("activity_date", desc=True) \
                .limit(1) \
                .execute()
            if res.data:
                matched_row = res.data[0]
                print(f"[Status Webhook] ✅ Layer 5 HIT: email-only match -> {matched_row['tw_confirmation']}")
        except Exception as e:
            print(f"[Status Webhook] Layer 5 error: {e}")

    # --- Layer 6: Race condition fallback for empty customer objects (Rentals) ---
    if not matched_row:
        import time
        print(f"[Status Webhook] No match yet. Waiting 3s for sibling Trip Updated webhook to arrive...")
        time.sleep(3)
        try:
            res = supabase.table("update_webhooks").select("tw_confirmation, payload").order("created_at", desc=True).limit(20).execute()
            for r in res.data or []:
                payload_str = json.dumps(r.get("payload", {}))
                if str(booking_id) in payload_str:
                    matched_row = {"tw_confirmation": r["tw_confirmation"]}
                    print(f"[Status Webhook] ✅ Layer 6 HIT: Found booking_id in update_webhooks queue -> {matched_row['tw_confirmation']}")
                    break
        except Exception as e:
            print(f"[Status Webhook] Layer 6 error: {e}")

    if not matched_row:
        print(f"[Status Webhook] ❌ No match found across all 6 layers for booking_id={booking_id}")
        return {"status": "queued", "note": "no matching reservation found"}

    tw_conf = matched_row["tw_confirmation"]
    print(f"[Status Webhook] Matched {tw_conf} -> new status: '{status_name}'")

    # Self-healing: backfill booking ID for future fast-path matching
    existing_ids = matched_row.get("tw_booking_ids") or []
    if booking_id not in existing_ids:
        try:
            new_ids = existing_ids + [booking_id]
            update_multiple_fields(tw_conf, {"tw_booking_ids": new_ids})
            print(f"[Status Webhook] 🔧 Backfilled booking_id={booking_id} into {tw_conf}")
        except Exception:
            pass  # Non-fatal

    # 4. Map TripWorks status to DB updates
    updates = {"tw_status": status_name, "last_updated": datetime.now(MDT).isoformat()}

    if status_name in _ON_RIDE_STATUSES:  # "Checked In", "Rental Out", "No Show"
        updates["checked_in"] = True
        updates["checked_in_at"] = datetime.now(MDT).isoformat()
        if status_name == "Rental Out":
            updates["rental_status"] = "On Ride"
    elif status_name in _RETURNED_STATUSES:  # "Rental Returned"
        updates["rental_status"] = "Returned"
    elif status_name == "Not Checked In":
        # Reset — staff correction / undo
        updates["checked_in"] = False
        updates["checked_in_at"] = None
        updates["rental_status"] = ""
    # Other statuses (Ready to Ride, Upgrade/Deposit, MPWR Waiver Required)
    # are informational only — just store tw_status

    # 5. Update Supabase
    try:
        update_multiple_fields(tw_conf, updates)
        print(f"[Status Webhook] Updated {tw_conf}: {updates}")
    except Exception as e:
        print(f"[Status Webhook] DB update failed for {tw_conf}: {e}")
        return {"status": "error", "reason": str(e)}

    # 6. Trigger real-time cache refresh + WebSocket broadcast
    try:
        _refresh_cache_sync()
        if _main_loop and _arrival_cache:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "update", "arrivals": _arrival_cache.model_dump()}),
                _main_loop
            )
        print(f"[Status Webhook] Cache refreshed and broadcast sent")
    except Exception as e:
        print(f"[Status Webhook] Cache refresh/broadcast failed: {e}")

    return {"status": "processed", "tw_confirmation": tw_conf, "new_status": status_name}


@app.post("/api/webhook/tw-payment-received")
async def tw_payment_received(request: Request):
    """
    Inline handler for TripWorks payment webhooks.
    Updates balance due/paid columns and deposit status.
    When due == 0, marks deposit as "Collected".
    
    Also enriches any missing reservation data from the trip object.

    Payload structure (confirmed from TripWorks docs):
    {
      "id": 1277113,                // payment ID
      "amount": 5000,               // cents
      "status": {"name": "Successful"},
      "type": {"name": "Cash"},
      "direction": {"name": "Payment"},
      "trip": {
        "confirmation_code": "WRYW-DHHJ",
        "subtotal": 96000,          // cents
        "total": 106377,            // cents  
        "paid": 5000,               // cents
        "due": 101377,              // cents
        "tripOrders": [...],
        "customer": {...}
      }
    }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Bad Request: Expected JSON")

    # 1. Save raw payload to dedicated cache directory and Supabase Queue for local agent
    try:
        cache_dir = os.path.join(os.path.dirname(__file__), "payment_webhook_cache")
        os.makedirs(cache_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cache_path = os.path.join(cache_dir, f"payment_{ts}.json")
        with open(cache_path, "w") as f:
            json.dump(body, f, indent=2)
            
        # Queue for local MPWR Payment Agent
        supabase = get_supabase()
        trip_conf = body.get("trip", {}).get("confirmation_code")
        headers_dict = dict(request.headers)
        
        payload_str = json.dumps(body, sort_keys=True)
        payload_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
        
        # Deduplication check
        existing_wh = supabase.table("pending_payment_webhooks").select("id").eq("payload_hash", payload_hash).limit(1).execute()
        
        if existing_wh.data:
            print(f"[Payment Webhook] Duplicate webhook detected for {trip_conf or 'unknown'}. Skipping insert.")
        else:
            supabase.table("pending_payment_webhooks").insert({
                "tw_confirmation": trip_conf,
                "headers": headers_dict,
                "payload": body,
                "payload_hash": payload_hash,
                "status": "pending"
            }).execute()
            print(f"[Payment Webhook] Queued payment event for {trip_conf or 'unknown'}")
    except Exception as e:
        print(f"[Payment Webhook] Cache/Queue save failed: {e}")

    # 2. Extract trip data — payment webhooks nest everything under "trip"
    trip = body.get("trip", {})
    tw_conf = trip.get("confirmation_code", "")
    payment_status = body.get("status", {}).get("name", "")
    payment_type = body.get("type", {}).get("name", "")
    payment_direction = body.get("direction", {}).get("name", "")
    amount_cents = body.get("amount", 0)
    due_cents = trip.get("due", -1)  # -1 = not present
    paid_cents = trip.get("paid", 0)
    owner_name = body.get("owner", {}).get("full_name", "")

    print(f"[Payment Webhook] Received: tw_conf={tw_conf}, payment=${amount_cents/100:.2f} "
          f"{payment_type} ({payment_status}), due=${due_cents/100:.2f}, by={owner_name}")

    if not tw_conf:
        print(f"[Payment Webhook] Missing confirmation_code, skipping")
        return {"status": "skipped", "reason": "missing confirmation_code"}

    # 3. Only process successful payments
    if payment_status != "Successful":
        print(f"[Payment Webhook] Non-successful payment status: {payment_status}, skipping update")
        return {"status": "skipped", "reason": f"payment status: {payment_status}"}

    # 4. Check if reservation exists
    try:
        supabase = get_supabase()
        existing = supabase.table("reservations") \
            .select("tw_confirmation, deposit_status, amount_due, amount_paid") \
            .eq("tw_confirmation", tw_conf.upper()) \
            .execute()
    except Exception as e:
        print(f"[Payment Webhook] DB lookup failed: {e}")
        return {"status": "error", "reason": str(e)}

    if not existing.data:
        print(f"[Payment Webhook] No reservation found for {tw_conf} — will enrich when created")
        return {"status": "queued", "note": "reservation not yet created"}

    # 5. Build payment updates
    updates = {
        "amount_paid": paid_cents / 100.0,
        "last_updated": datetime.now(MDT).isoformat(),
    }
    if due_cents >= 0:
        updates["amount_due"] = due_cents / 100.0

    # Only mark as Collected when ENTIRE balance is paid (due == 0)
    if due_cents == 0:
        updates["deposit_status"] = "Collected"
        if owner_name:
            updates["payment_collected_by"] = owner_name
        print(f"[Payment Webhook] {tw_conf}: Balance PAID IN FULL -> Deposit: Collected")
    else:
        # Partial payment — keep deposit as Due (unless manually set to Compensated)
        current_status = existing.data[0].get("deposit_status", "")
        if current_status != "Compensated":
            updates["deposit_status"] = "Due"
        print(f"[Payment Webhook] {tw_conf}: Partial payment. Due: ${due_cents/100:.2f}")

    # 6. Update financial columns
    try:
        update_multiple_fields(tw_conf.upper(), updates)
        print(f"[Payment Webhook] Updated {tw_conf}: {updates}")
    except Exception as e:
        print(f"[Payment Webhook] DB update failed for {tw_conf}: {e}")
        return {"status": "error", "reason": str(e)}

    # 7. Opportunistic enrichment — fill in any other missing data from the trip object
    try:
        _enrich_reservation_from_payload(tw_conf, body)
    except Exception as e:
        print(f"[Payment Webhook] Enrichment failed (non-fatal): {e}")

    # 8. Trigger real-time cache refresh + WebSocket broadcast
    try:
        _refresh_cache_sync()
        if _main_loop and _arrival_cache:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "update", "arrivals": _arrival_cache.model_dump()}),
                _main_loop
            )
        print(f"[Payment Webhook] Cache refreshed and broadcast sent")
    except Exception as e:
        print(f"[Payment Webhook] Cache refresh/broadcast failed: {e}")

    return {
        "status": "processed",
        "tw_confirmation": tw_conf,
        "amount": amount_cents / 100.0,
        "due": due_cents / 100.0 if due_cents >= 0 else None,
        "deposit_status": updates.get("deposit_status", "")
    }


# =============================================================================
# HEALTH & UTILITY
# =============================================================================

@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "server_time": datetime.now(MDT).isoformat(),
        "cache_age_seconds": (
            (datetime.now(MDT) - _cache_timestamp).total_seconds()
            if _cache_timestamp else None
        ),
    }


@app.post("/api/refresh")
def force_refresh(request: Request):
    """Force a cache refresh from Supabase. Protected by API key + rate limited."""
    api_key = os.getenv("DASHBOARD_API_KEY", "")
    if api_key and request.headers.get("X-API-Key") != api_key:
        raise HTTPException(403, "Invalid API key")

    # Rate limit: prevent abuse (max 1 refresh per REFRESH_COOLDOWN seconds per true IP)
    client_ip = get_client_ip(request)
    now_ts = time.time()
    last_ts = _refresh_timestamps.get(client_ip, 0)
    if now_ts - last_ts < REFRESH_COOLDOWN:
        raise HTTPException(429, f"Rate limited. Wait {REFRESH_COOLDOWN}s between refreshes.")
    _refresh_timestamps[client_ip] = now_ts

    _refresh_cache_sync()
    return {"message": "Cache refreshed", "arrivals": _arrival_cache.total_today if _arrival_cache else 0}


# =============================================================================
# STATIC FILES & SPA ROUTING
# =============================================================================

# Mount static assets from the Vite build
# In production (Railway): frontend is copied to backend/static/
# Locally: falls back to ../frontend/dist
frontend_dist = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(frontend_dist):
    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
frontend_assets = os.path.join(frontend_dist, "assets")

if os.path.exists(frontend_assets):
    app.mount("/assets", StaticFiles(directory=frontend_assets), name="assets")

# SPA catch-all: serve static files first, then index.html for SPA routes
@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    """Serve static files or the React SPA for all frontend routes."""
    # First, check if the requested file exists (logos, favicon, etc.)
    if full_path:
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
    
    # Otherwise, serve index.html for SPA routing
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        {"error": "Frontend not built. Run 'npm run build' in frontend/"},
        status_code=503,
    )
