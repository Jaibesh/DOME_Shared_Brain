"""
Backfill tw_booking_ids for all reservations that are missing them.

Strategy:
  1. Query Supabase for reservations missing tw_booking_ids
  2. Group by activity_date
  3. For each date, hit TripWorks API: POST /api/manifest/getManifestOnDay/{date}
  4. Match by confirmation_code -> extract booking IDs
  5. Update Supabase

Requires a valid TripWorksSession-prod cookie (expires periodically).
"""
import os, sys, time, json
from datetime import datetime, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()
import requests
from supabase import create_client

# ── Config ──────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TW_BASE = "https://epic4x4.tripworks.com"
TW_COOKIE_NAME = "TripWorksSession-prod"
TW_COOKIE_VALUE = os.getenv("TW_SESSION_COOKIE", "r4odf3um2rec2c36c722l81d5c")

# ── TripWorks session ───────────────────────────────────────────────────
tw = requests.Session()
tw.cookies.set(TW_COOKIE_NAME, TW_COOKIE_VALUE, domain=".tripworks.com", path="/")
tw.headers.update({
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "X-Timezone": "America/Denver",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})


def verify_tw_auth():
    """Quick check that the cookie is still valid."""
    r = tw.get(f"{TW_BASE}/api/account/get", timeout=10)
    if r.status_code != 200:
        print("FATAL: TripWorks session cookie is expired or invalid.")
        print("       Get a fresh cookie from browser DevTools > Application > Cookies")
        sys.exit(1)
    print("TripWorks auth OK\n")


def fetch_manifest_for_date(date_str: str) -> dict:
    """
    Returns {confirmation_code: [booking_id, ...]} for a given date.
    date_str format: YYYY-MM-DD
    """
    url = f"{TW_BASE}/api/manifest/getManifestOnDay/{date_str}"
    r = tw.post(url, json={}, timeout=30)
    if r.status_code != 200:
        print(f"  WARN: Manifest API returned {r.status_code} for {date_str}")
        return {}

    data = r.json()
    mapping = {}
    for trip_order in data.get("tripOrders", []):
        trip = trip_order.get("trip", {})
        conf_code = trip.get("confirmation_code", "")
        if not conf_code:
            continue

        booking_ids = []
        for b in trip_order.get("bookings", []):
            bid = b.get("id")
            if bid and isinstance(bid, int):
                booking_ids.append(bid)

        order_id = trip_order.get("id")
        if booking_ids:
            mapping[conf_code] = {
                "booking_ids": booking_ids,
                "order_id": str(order_id) if order_id else "",
            }

    return mapping


def main():
    verify_tw_auth()

    # ── Step 1: Get all reservations missing tw_booking_ids ──────────
    print("Querying Supabase for reservations missing tw_booking_ids...")
    res = (
        supabase.table("reservations")
        .select("tw_confirmation,guest_name,activity_date,tw_booking_ids,tw_order_id")
        .execute()
    )
    all_rows = res.data
    missing = [r for r in all_rows if not r.get("tw_booking_ids")]
    print(f"  Total reservations: {len(all_rows)}")
    print(f"  Missing tw_booking_ids: {len(missing)}")

    if not missing:
        print("\nAll reservations have booking IDs. Nothing to do!")
        return

    # ── Step 2: Group by activity_date ───────────────────────────────
    by_date = defaultdict(list)
    no_date = []
    for row in missing:
        date = row.get("activity_date", "")
        if date:
            # Normalize date format
            for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
                try:
                    parsed = datetime.strptime(date, fmt)
                    date = parsed.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            by_date[date].append(row)
        else:
            no_date.append(row)

    dates_sorted = sorted(by_date.keys())
    print(f"  Spanning {len(dates_sorted)} unique dates: {dates_sorted[0]} .. {dates_sorted[-1]}")
    if no_date:
        print(f"  WARNING: {len(no_date)} reservations have no activity_date")

    # ── Step 3: For each date, fetch manifest and match ──────────────
    fixed = 0
    not_found_in_manifest = []
    api_errors = 0

    for i, date in enumerate(dates_sorted):
        rows = by_date[date]
        conf_codes_needed = {r["tw_confirmation"] for r in rows}

        print(f"\n[{i+1}/{len(dates_sorted)}] {date} — {len(rows)} reservations to backfill")

        # Fetch from TripWorks
        mapping = fetch_manifest_for_date(date)
        if not mapping:
            print(f"  No manifest data returned (possibly no trips on this date)")
            not_found_in_manifest.extend(rows)
            continue

        print(f"  Manifest returned {len(mapping)} trip orders")

        for row in rows:
            conf = row["tw_confirmation"]
            if conf not in mapping:
                not_found_in_manifest.append(row)
                continue

            info = mapping[conf]
            booking_ids = info["booking_ids"]
            order_id = info["order_id"]

            updates = {"tw_booking_ids": booking_ids}
            if order_id and not row.get("tw_order_id"):
                updates["tw_order_id"] = order_id

            try:
                supabase.table("reservations").update(updates).eq(
                    "tw_confirmation", conf
                ).execute()
                fixed += 1
                print(f"    OK: {conf} ({row['guest_name']}) -> booking_ids={booking_ids}")
            except Exception as e:
                api_errors += 1
                print(f"    FAIL: {conf}: {e}")

        # Be polite to TripWorks API
        time.sleep(0.5)

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"BACKFILL COMPLETE")
    print(f"  Fixed:               {fixed}")
    print(f"  Not in manifest:     {len(not_found_in_manifest)}")
    print(f"  API errors:          {api_errors}")
    print(f"  Total missing:       {len(missing)}")
    print("=" * 60)

    if not_found_in_manifest:
        print(f"\nReservations NOT found in TripWorks manifest ({len(not_found_in_manifest)}):")
        for row in not_found_in_manifest:
            print(f"  {row['tw_confirmation']}  {row.get('activity_date', '??')}  {row['guest_name']}")


if __name__ == "__main__":
    main()
