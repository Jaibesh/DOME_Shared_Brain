"""
reconcile_database.py — One-time Supabase ↔ Zapier Google Sheet Reconciliation

Cross-references the Supabase reservations table against the Zapier-powered
Guest Readiness Google Sheet (source of truth).

Actions:
  - FIX_MPWR:  Copy missing MPOWR numbers from the Sheet to Supabase
  - FIX_NAME:  Correct mismatched guest names
  - FIX_BOTH:  Fix both MPOWR and name
  - ORPHAN:    Delete Supabase rows that don't exist in the Sheet
  - MATCH:     No action needed

Usage:
  python scripts/reconcile_database.py           # Dry run (audit only)
  python scripts/reconcile_database.py --live     # Execute changes
"""

import os
import re
import sys
import argparse
from datetime import datetime, timedelta

# Force UTF-8 output on Windows terminals
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv

# Load env from the Reservation Agent root
AGENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(AGENT_ROOT, ".env"))

# Also load from Payment Agent (has same Supabase creds)
PAYMENT_AGENT_ENV = os.path.join(
    os.path.dirname(AGENT_ROOT), "MPWR_Payment_Agent", ".env"
)
if os.path.exists(PAYMENT_AGENT_ENV):
    load_dotenv(PAYMENT_AGENT_ENV, override=False)

import gspread
from supabase import create_client


# =============================================================================
# Constants
# =============================================================================
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "10DIqgwuWgTsi69ObujEOaBbdPz-HHRbzn9mCw2cEc4g")

# Sentinel MPOWR values that are NOT real IDs
_INVALID_MPWR_IDS = {"UNKNOWN", "EXISTS", "ERROR", "DRY_RUN", "EXTRACTION_FAILED", "RETRY", ""}

# Regex for a valid MPOWR confirmation code (e.g., CO-Y86-RQP)
_MPWR_PATTERN = re.compile(r'^[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+$', re.IGNORECASE)


# =============================================================================
# Helpers
# =============================================================================
def _clean_mpwr_id(raw: str) -> str | None:
    """
    Clean a raw MPOWR value from the Google Sheet.
    Returns the cleaned ID or None if invalid.
    """
    if not raw:
        return None

    raw = raw.strip()

    # Skip known bad prefixes
    for prefix in ["ERROR", "RETRY", "UNKNOWN", "EXISTS"]:
        if raw.upper().startswith(prefix):
            return None

    # Strip prefixes like "DUPLICATE: ", "DRY_RUN: "
    for prefix in ["DUPLICATE: ", "DRY_RUN: ", "DUPLICATE:", "DRY_RUN:"]:
        raw = raw.replace(prefix, "").strip()

    if not raw or raw.upper() in _INVALID_MPWR_IDS:
        return None

    # For multi-vehicle bookings, keep the full comma-separated string
    # but validate each part
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    valid_parts = []
    for part in parts:
        if _MPWR_PATTERN.match(part):
            valid_parts.append(part)

    if valid_parts:
        return ", ".join(valid_parts)

    return None


def _normalize_name(first: str, last: str) -> str:
    """Build a normalized full name from first + last."""
    first = str(first or "").strip()
    last = str(last or "").strip()
    return f"{first} {last}".strip()


def _names_match(supabase_name: str, sheet_name: str) -> bool:
    """Case-insensitive name comparison. Handles CSV encoding artifacts
    (e.g., François → FranÃ§ois) by also comparing ASCII-normalized forms."""
    a = supabase_name.strip().lower()
    b = sheet_name.strip().lower()
    if a == b:
        return True
    # CSV export can garble UTF-8 characters. If the ASCII-only characters match,
    # treat them as equivalent to avoid downgrading correct UTF-8 data.
    import unicodedata
    a_ascii = unicodedata.normalize('NFKD', a).encode('ascii', 'ignore').decode()
    b_ascii = unicodedata.normalize('NFKD', b).encode('ascii', 'ignore').decode()
    return a_ascii == b_ascii


# =============================================================================
# Data Loading
# =============================================================================
def load_google_sheet() -> dict:
    """
    Load all records from the Zapier Google Sheet.
    Uses CSV export (no OAuth needed if sheet is accessible) or falls back to gspread.
    Returns a dict keyed by uppercase TW Confirmation.
    """
    import csv
    import io
    import requests

    print("[Sheet] Attempting to load via CSV export...")
    
    # Try CSV export first (works if sheet is shared with "Anyone with the link")
    csv_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv&gid=0"
    
    try:
        resp = requests.get(csv_url, timeout=30)
        if resp.status_code == 200 and not resp.text.startswith("<!DOCTYPE"):
            print(f"[Sheet] CSV export successful ({len(resp.text)} bytes)")
            reader = csv.DictReader(io.StringIO(resp.text))
            records = list(reader)
        else:
            print(f"[Sheet] CSV export returned status {resp.status_code} or HTML (sheet may not be public)")
            print("[Sheet] Falling back to gspread OAuth...")
            records = _load_via_gspread()
    except Exception as e:
        print(f"[Sheet] CSV export failed: {e}")
        print("[Sheet] Falling back to gspread OAuth...")
        records = _load_via_gspread()

    print(f"[Sheet] Loaded {len(records)} rows from Zapier Sheet")

    # Index by TW Confirmation (uppercase)
    sheet_data = {}
    for row in records:
        tw_conf = str(
            row.get("TW Confirmation", "") or row.get("Confirmation Code", "")
        ).strip().upper()

        if not tw_conf:
            continue

        first = str(row.get("First Name", "")).strip()
        last = str(row.get("Last Name", "")).strip()
        raw_mpwr = str(row.get("MPWR Confirmation Number", "")).strip()

        sheet_data[tw_conf] = {
            "tw_confirmation": tw_conf,
            "guest_name": _normalize_name(first, last),
            "mpwr_number": _clean_mpwr_id(raw_mpwr),
            "raw_mpwr": raw_mpwr,
            "activity": str(row.get("Activity", "")).strip(),
            "activity_date": str(row.get("Activity Date", "")).strip(),
            "activity_time": str(row.get("Activity Time", "")).strip(),
        }

    print(f"[Sheet] Indexed {len(sheet_data)} unique TW confirmations")
    return sheet_data


def _load_via_gspread() -> list:
    """Fallback: load via gspread OAuth (requires interactive browser flow)."""
    workspace_root = os.path.dirname(AGENT_ROOT)
    client_secret_files = [
        f for f in os.listdir(workspace_root)
        if f.startswith("client_secret") and f.endswith(".json")
    ]

    if not client_secret_files:
        print("[Sheet] ERROR: No client_secret*.json found in workspace root!")
        sys.exit(1)

    client_secret_path = os.path.join(workspace_root, client_secret_files[0])
    gc = gspread.oauth(
        credentials_filename=client_secret_path,
        authorized_user_filename=os.path.join(workspace_root, "authorized_user.json"),
    )

    sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1
    return sheet.get_all_records(value_render_option="FORMATTED_VALUE")


def load_supabase() -> dict:
    """
    Load all records from Supabase reservations table.
    Returns a dict keyed by uppercase tw_confirmation.
    """
    print("[Supabase] Connecting...")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("[Supabase] ERROR: Missing SUPABASE_URL or SUPABASE_KEY")
        sys.exit(1)

    supabase = create_client(url, key)

    # Fetch all rows (paginated if needed)
    print("[Supabase] Fetching all reservations...")
    res = supabase.table("reservations").select(
        "tw_confirmation, guest_name, mpwr_number, activity_name, activity_date, activity_time"
    ).execute()

    rows = res.data or []
    print(f"[Supabase] Loaded {len(rows)} rows")

    # Index by TW confirmation (uppercase)
    sb_data = {}
    for row in rows:
        tw_conf = str(row.get("tw_confirmation", "")).strip().upper()
        if tw_conf:
            sb_data[tw_conf] = row

    print(f"[Supabase] Indexed {len(sb_data)} unique TW confirmations")
    return sb_data


# =============================================================================
# Reconciliation Logic
# =============================================================================
def reconcile(sheet_data: dict, sb_data: dict) -> dict:
    """
    Cross-reference Sheet and Supabase and classify each row.
    Returns a dict of classification buckets.
    """
    buckets = {
        "MATCH": [],
        "FIX_MPWR": [],
        "FIX_NAME": [],
        "FIX_BOTH": [],
        "ORPHAN": [],
        "SHEET_ONLY": [],
    }

    # Check every Supabase row against the Sheet
    for tw_conf, sb_row in sb_data.items():
        sb_name = str(sb_row.get("guest_name", "") or "").strip()
        sb_mpwr = str(sb_row.get("mpwr_number", "") or "").strip()

        if tw_conf in sheet_data:
            sheet_row = sheet_data[tw_conf]
            sheet_name = sheet_row["guest_name"]
            sheet_mpwr = sheet_row["mpwr_number"]  # Already cleaned

            needs_mpwr_fix = False
            needs_name_fix = False

            # Check MPOWR: fix if Supabase is missing/invalid/URL AND Sheet has valid
            sb_mpwr_is_valid = bool(sb_mpwr and _MPWR_PATTERN.match(sb_mpwr.split(",")[0].strip()))
            if not sb_mpwr_is_valid and sheet_mpwr:
                needs_mpwr_fix = True

            # Check name: only fix if names don't match and sheet has a real name
            if sb_name and sheet_name and not _names_match(sb_name, sheet_name):
                needs_name_fix = True

            if needs_mpwr_fix and needs_name_fix:
                buckets["FIX_BOTH"].append({
                    "tw_conf": tw_conf,
                    "sb_name": sb_name, "sheet_name": sheet_name,
                    "sb_mpwr": sb_mpwr, "sheet_mpwr": sheet_mpwr,
                    "activity": sheet_row.get("activity", ""),
                    "date": sheet_row.get("activity_date", ""),
                })
            elif needs_mpwr_fix:
                buckets["FIX_MPWR"].append({
                    "tw_conf": tw_conf,
                    "sb_name": sb_name,
                    "sb_mpwr": sb_mpwr, "sheet_mpwr": sheet_mpwr,
                    "activity": sheet_row.get("activity", ""),
                    "date": sheet_row.get("activity_date", ""),
                })
            elif needs_name_fix:
                buckets["FIX_NAME"].append({
                    "tw_conf": tw_conf,
                    "sb_name": sb_name, "sheet_name": sheet_name,
                    "sb_mpwr": sb_mpwr,
                    "activity": sheet_row.get("activity", ""),
                    "date": sheet_row.get("activity_date", ""),
                })
            else:
                buckets["MATCH"].append({"tw_conf": tw_conf})
        else:
            # Supabase row NOT in Google Sheet → orphan
            buckets["ORPHAN"].append({
                "tw_conf": tw_conf,
                "sb_name": sb_name,
                "sb_mpwr": sb_mpwr,
                "activity": str(sb_row.get("activity_name", "") or ""),
                "date": str(sb_row.get("activity_date", "") or ""),
            })

    # Check for Sheet rows not in Supabase
    for tw_conf, sheet_row in sheet_data.items():
        if tw_conf not in sb_data:
            buckets["SHEET_ONLY"].append({
                "tw_conf": tw_conf,
                "sheet_name": sheet_row["guest_name"],
                "sheet_mpwr": sheet_row["mpwr_number"],
                "activity": sheet_row.get("activity", ""),
                "date": sheet_row.get("activity_date", ""),
            })

    return buckets


# =============================================================================
# Reporting
# =============================================================================
def print_report(buckets: dict):
    """Print a detailed audit report."""
    print("\n" + "=" * 80)
    print("  DATABASE RECONCILIATION AUDIT REPORT")
    print("=" * 80)

    # Summary
    print(f"\n  ✅ MATCH (no action):     {len(buckets['MATCH']):>4}")
    print(f"  🔧 FIX_MPWR:             {len(buckets['FIX_MPWR']):>4}")
    print(f"  🔧 FIX_NAME:             {len(buckets['FIX_NAME']):>4}")
    print(f"  🔧 FIX_BOTH:             {len(buckets['FIX_BOTH']):>4}")
    print(f"  🗑️  ORPHAN (to delete):   {len(buckets['ORPHAN']):>4}")
    print(f"  ⚠️  SHEET_ONLY (info):    {len(buckets['SHEET_ONLY']):>4}")
    total_fixes = len(buckets['FIX_MPWR']) + len(buckets['FIX_NAME']) + len(buckets['FIX_BOTH'])
    print(f"\n  TOTAL FIXES:  {total_fixes}")
    print(f"  TOTAL DELETES: {len(buckets['ORPHAN'])}")

    # Detail: FIX_MPWR
    if buckets["FIX_MPWR"]:
        print(f"\n{'─' * 80}")
        print("  🔧 FIX_MPWR — Missing MPOWR numbers to fill from Sheet")
        print(f"{'─' * 80}")
        for r in buckets["FIX_MPWR"]:
            print(f"  {r['tw_conf']:12s} | {r['sb_name']:30s} | '{r['sb_mpwr']}' → '{r['sheet_mpwr']}' | {r['activity'][:35]} | {r['date']}")

    # Detail: FIX_NAME
    if buckets["FIX_NAME"]:
        print(f"\n{'─' * 80}")
        print("  🔧 FIX_NAME — Guest names to correct")
        print(f"{'─' * 80}")
        for r in buckets["FIX_NAME"]:
            print(f"  {r['tw_conf']:12s} | '{r['sb_name']}' → '{r['sheet_name']}' | MPWR: {r['sb_mpwr']}")

    # Detail: FIX_BOTH
    if buckets["FIX_BOTH"]:
        print(f"\n{'─' * 80}")
        print("  🔧 FIX_BOTH — Both MPOWR and name need fixing")
        print(f"{'─' * 80}")
        for r in buckets["FIX_BOTH"]:
            print(f"  {r['tw_conf']:12s}")
            print(f"    Name: '{r['sb_name']}' → '{r['sheet_name']}'")
            print(f"    MPWR: '{r['sb_mpwr']}' → '{r['sheet_mpwr']}'")

    # Detail: ORPHAN
    if buckets["ORPHAN"]:
        print(f"\n{'─' * 80}")
        print("  🗑️  ORPHAN — Supabase rows NOT in Google Sheet (will be deleted)")
        print(f"{'─' * 80}")
        for r in buckets["ORPHAN"]:
            print(f"  {r['tw_conf']:12s} | {r['sb_name']:30s} | MPWR: {r['sb_mpwr'] or 'NULL':15s} | {r['activity'][:35]} | {r['date']}")

    # Detail: SHEET_ONLY
    if buckets["SHEET_ONLY"]:
        print(f"\n{'─' * 80}")
        print("  ⚠️  SHEET_ONLY — In Google Sheet but NOT in Supabase (info only)")
        print(f"{'─' * 80}")
        for r in buckets["SHEET_ONLY"][:20]:  # Cap at 20 for readability
            print(f"  {r['tw_conf']:12s} | {r['sheet_name']:30s} | MPWR: {r['sheet_mpwr'] or 'N/A':15s} | {r['activity'][:35]} | {r['date']}")
        if len(buckets["SHEET_ONLY"]) > 20:
            print(f"  ... and {len(buckets['SHEET_ONLY']) - 20} more")

    print(f"\n{'=' * 80}\n")


# =============================================================================
# Execution
# =============================================================================
def execute_changes(buckets: dict):
    """Apply all classified changes to Supabase."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    supabase = create_client(url, key)

    now = datetime.utcnow().isoformat()
    stats = {"mpwr_fixed": 0, "name_fixed": 0, "both_fixed": 0, "deleted": 0, "errors": 0}

    # FIX_MPWR
    for r in buckets["FIX_MPWR"]:
        try:
            supabase.table("reservations").update({
                "mpwr_number": r["sheet_mpwr"],
                "last_updated": now,
            }).eq("tw_confirmation", r["tw_conf"]).execute()
            print(f"  ✅ {r['tw_conf']}: mpwr_number set to '{r['sheet_mpwr']}'")
            stats["mpwr_fixed"] += 1
        except Exception as e:
            print(f"  ❌ {r['tw_conf']}: Failed to update MPWR: {e}")
            stats["errors"] += 1

    # FIX_NAME
    for r in buckets["FIX_NAME"]:
        try:
            supabase.table("reservations").update({
                "guest_name": r["sheet_name"],
                "last_updated": now,
            }).eq("tw_confirmation", r["tw_conf"]).execute()
            print(f"  ✅ {r['tw_conf']}: guest_name '{r['sb_name']}' → '{r['sheet_name']}'")
            stats["name_fixed"] += 1
        except Exception as e:
            print(f"  ❌ {r['tw_conf']}: Failed to update name: {e}")
            stats["errors"] += 1

    # FIX_BOTH
    for r in buckets["FIX_BOTH"]:
        try:
            supabase.table("reservations").update({
                "mpwr_number": r["sheet_mpwr"],
                "guest_name": r["sheet_name"],
                "last_updated": now,
            }).eq("tw_confirmation", r["tw_conf"]).execute()
            print(f"  ✅ {r['tw_conf']}: name → '{r['sheet_name']}', mpwr → '{r['sheet_mpwr']}'")
            stats["both_fixed"] += 1
        except Exception as e:
            print(f"  ❌ {r['tw_conf']}: Failed to update both: {e}")
            stats["errors"] += 1

    # ORPHAN — Delete
    for r in buckets["ORPHAN"]:
        try:
            supabase.table("reservations").delete().eq(
                "tw_confirmation", r["tw_conf"]
            ).execute()
            print(f"  🗑️  {r['tw_conf']}: DELETED (orphan — {r['sb_name']})")
            stats["deleted"] += 1
        except Exception as e:
            print(f"  ❌ {r['tw_conf']}: Failed to delete: {e}")
            stats["errors"] += 1

    print(f"\n{'=' * 80}")
    print("  EXECUTION SUMMARY")
    print(f"{'=' * 80}")
    print(f"  MPOWR fixed:  {stats['mpwr_fixed']}")
    print(f"  Names fixed:  {stats['name_fixed']}")
    print(f"  Both fixed:   {stats['both_fixed']}")
    print(f"  Deleted:      {stats['deleted']}")
    print(f"  Errors:       {stats['errors']}")
    print(f"{'=' * 80}\n")


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Reconcile Supabase ↔ Google Sheet")
    parser.add_argument("--live", action="store_true", help="Execute changes (default is dry-run)")
    args = parser.parse_args()

    print(f"\n{'=' * 80}")
    print(f"  DATABASE RECONCILIATION — {'LIVE RUN' if args.live else 'DRY RUN (audit only)'}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}\n")

    # Load data from both sources
    sheet_data = load_google_sheet()
    sb_data = load_supabase()

    # Cross-reference
    print("\n[Reconcile] Cross-referencing data...")
    buckets = reconcile(sheet_data, sb_data)

    # Print report
    print_report(buckets)

    if not args.live:
        print("  ℹ️  This was a DRY RUN. No changes were made.")
        print("  ℹ️  To execute changes, run with --live flag.\n")
        return

    # Live run — ask for confirmation
    total_changes = (
        len(buckets["FIX_MPWR"]) + len(buckets["FIX_NAME"]) +
        len(buckets["FIX_BOTH"]) + len(buckets["ORPHAN"])
    )

    if total_changes == 0:
        print("  ✅ Nothing to do — database is already in sync!\n")
        return

    print(f"  ⚠️  About to make {total_changes} changes to the database.")
    confirm = input("  Are you sure? (y/N): ").strip().lower()

    if confirm != "y":
        print("  ❌ Aborted. No changes made.\n")
        return

    print(f"\n{'─' * 80}")
    print("  Executing changes...")
    print(f"{'─' * 80}\n")

    execute_changes(buckets)


if __name__ == "__main__":
    main()
