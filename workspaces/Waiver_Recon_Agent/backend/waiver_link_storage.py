"""
waiver_link_storage.py — Supabase Storage & Database Helper for Waiver QR Codes

Handles:
  1. Uploading QR code PNG images to Supabase Storage (bucket: waiver-qr-codes)
  2. Updating the reservations table with the unique waiver link + QR code URL
  3. Querying for reservations that need waiver links scraped
"""

import os
from datetime import datetime

import pytz
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

MDT = pytz.timezone("America/Denver")

# The generic link that needs to be replaced
GENERIC_WAIVER_LINK = "https://adventures.polaris.com/our-outfitters/epic-4x4-adventures-O-DZ6-478/waiver/rider-info"

STORAGE_BUCKET = "waiver-qr-codes"

# Module-level cached Supabase client (avoid recreating on every call during large batches)
_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Initialize and cache Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _supabase_client = create_client(supabase_url=url, supabase_key=key)
    return _supabase_client


def get_reservations_needing_waiver_links() -> list[dict]:
    """
    Query Supabase for upcoming reservations that have an MPWR number
    but are missing their unique waiver link.

    A reservation "needs" a waiver link if:
      - mpwr_number is not empty
      - activity_date >= today
      - mpwr_waiver_link is NULL, empty, OR is the generic outfitter link
    """
    supabase = get_supabase()
    today_iso = datetime.now(MDT).date().isoformat()

    try:
        # Fetch all upcoming reservations with MPWR numbers
        res = supabase.table("reservations") \
            .select("tw_confirmation, mpwr_number, mpwr_waiver_link, activity_date, guest_name") \
            .gte("activity_date", today_iso) \
            .neq("mpwr_number", "") \
            .or_("mpwr_waiver_link.is.null,mpwr_waiver_link.eq.") \
            .execute()

        if not res.data:
            return []

        # Filter to those missing a proper unique link
        needing_links = []
        for r in res.data:
            mpwr_num = str(r.get("mpwr_number") or "").strip()
            if not mpwr_num or mpwr_num.upper() == "UNKNOWN":
                continue

            link = str(r.get("mpwr_waiver_link") or "").strip()

            # Needs scraping if: empty, matches generic link, or doesn't contain /join/
            if not link or link == GENERIC_WAIVER_LINK or "/join/" not in link:
                needing_links.append(r)

        return needing_links

    except Exception as e:
        print(f"[Storage] Error querying reservations: {e}")
        return []


def upload_qr_code(tw_conf: str, image_bytes: bytes) -> str | None:
    """
    Upload a QR code PNG to Supabase Storage.

    Args:
        tw_conf: TripWorks confirmation code (used as filename)
        image_bytes: Raw PNG bytes of the QR code image

    Returns:
        Public URL of the uploaded image, or None on failure
    """
    supabase = get_supabase()
    file_path = f"{tw_conf}.png"

    try:
        # Remove existing file if it exists (upsert behavior)
        try:
            supabase.storage.from_(STORAGE_BUCKET).remove([file_path])
        except Exception:
            pass  # File may not exist yet

        # Upload the new QR code
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=file_path,
            file=image_bytes,
            file_options={"content-type": "image/png", "upsert": "true"},
        )

        # Get the public URL
        public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(file_path)
        print(f"[Storage] ✅ Uploaded QR code for {tw_conf}: {public_url}")
        return public_url

    except Exception as e:
        print(f"[Storage] ❌ Failed to upload QR for {tw_conf}: {e}")
        return None


def update_reservation_waiver_link(tw_conf: str, waiver_link: str, qr_url: str | None = None) -> bool:
    """
    Update a reservation's waiver link and QR URL in Supabase.

    Args:
        tw_conf: TripWorks confirmation code
        waiver_link: The unique join URL (e.g., https://adventures.polaris.com/join/RES-42V-EK7)
        qr_url: Public URL to the QR code image in Supabase Storage

    Returns:
        True if update succeeded
    """
    supabase = get_supabase()

    try:
        updates = {
            "mpwr_waiver_link": waiver_link,
            "last_updated": datetime.now(MDT).isoformat(),
        }
        if qr_url:
            updates["mpwr_waiver_qr_url"] = qr_url

        res = supabase.table("reservations").update(updates).eq("tw_confirmation", tw_conf).execute()

        if res.data:
            print(f"[Storage] ✅ Updated waiver link for {tw_conf}")
            return True
        else:
            print(f"[Storage] ⚠️ No reservation found for {tw_conf}")
            return False

    except Exception as e:
        print(f"[Storage] ❌ Failed to update {tw_conf}: {e}")
        return False


def qr_code_exists(tw_conf: str) -> bool:
    """Check if a QR code already exists in Supabase Storage."""
    try:
        supabase = get_supabase()
        # Try to get public URL — if file doesn't exist, it'll still return a URL
        # but we can list the bucket to check
        result = supabase.storage.from_(STORAGE_BUCKET).list(path="", options={"search": tw_conf})
        return any(f.get("name", "").startswith(tw_conf) for f in (result or []))
    except Exception:
        return False
