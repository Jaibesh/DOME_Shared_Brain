import os
import sys
import time
from datetime import datetime, timedelta

# Add the parent directory to sys.path so we can import from the main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from sheets import get_sheets_client, write_dashboard_row
from data_mapper import map_legacy_to_dashboard

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

def convert_serial_date(serial):
    """Convert Google Sheets serial date to MM/DD/YYYY string"""
    base_date = datetime(1899, 12, 30)
    target_date = base_date + timedelta(days=int(float(serial)))
    return target_date.strftime("%m/%d/%Y")

def run_backfill():
    print(f"\n--- Starting Dashboard Backfill at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    client = get_sheets_client()
    if not client:
        print("[Error] Could not get Google Sheets client.")
        return
        
    primary_id = os.getenv("GOOGLE_SHEET_ID")
    dashboard_id = os.getenv("DASHBOARD_SHEET_ID")
    
    if not primary_id or not dashboard_id:
        print("[Error] Missing GOOGLE_SHEET_ID or DASHBOARD_SHEET_ID in .env")
        return
        
    print("Fetching V2 Dashboard records...")
    try:
        dash_sheet = client.open_by_key(dashboard_id).sheet1
        dash_records = dash_sheet.get_all_records()
    except Exception as e:
        print(f"[Error] Failed to fetch V2 Dashboard: {e}")
        return
        
    # Build a set of existing TW Confirmations to avoid duplicates
    existing_tw_confs = set(
        str(row.get("TW Confirmation", "")).strip().upper() 
        for row in dash_records if str(row.get("TW Confirmation", "")).strip()
    )
    print(f"-> Found {len(existing_tw_confs)} existing records in V2 Dashboard.")
    
    print("\nFetching Original Zapier Sheet records...")
    try:
        primary_sheet = client.open_by_key(primary_id).sheet1
        primary_records = primary_sheet.get_all_records()
    except Exception as e:
        print(f"[Error] Failed to fetch Primary Sheet: {e}")
        return
        
    print(f"-> Found {len(primary_records)} total rows in Zapier Sheet.")
    
    # Track statistics
    stats = {"migrated": 0, "skipped_duplicate": 0, "skipped_past": 0, "skipped_no_mpwr": 0, "errors": 0}
    
    today = datetime.now().date()
    
    print("\nProcessing rows...")
    for idx, row in enumerate(primary_records):
        tw_conf = str(row.get("TW Confirmation", "") or row.get("Confirmation Code", "")).strip().upper()
        raw_mpwr = str(row.get("MPWR Confirmation Number", "")).strip()
        
        # Skip empty rows
        if not tw_conf:
            continue
            
        # 1. Duplicate check
        if tw_conf in existing_tw_confs:
            stats["skipped_duplicate"] += 1
            continue
            
        # 2. Check for valid MPWR ID
        if not raw_mpwr or raw_mpwr.startswith("ERROR") or raw_mpwr.startswith("RETRY"):
            stats["skipped_no_mpwr"] += 1
            continue
            
        # Clean MPWR ID
        mpwr_id = raw_mpwr
        for prefix in ["DUPLICATE: ", "DRY_RUN: ", "DUPLICATE:", "DRY_RUN:"]:
            mpwr_id = mpwr_id.replace(prefix, "").strip()
        if "," in mpwr_id:
            mpwr_id = mpwr_id.split(",")[0].strip()
            
        if not mpwr_id:
            stats["skipped_no_mpwr"] += 1
            continue
            
        # 3. Filter by Date (Future or Today only)
        date_val = row.get("Activity Date", "")
        # Handle Excel/Google Sheets serial dates if present
        if isinstance(date_val, (int, float)) or (isinstance(date_val, str) and date_val.replace('.', '', 1).isdigit()):
            date_str = convert_serial_date(date_val)
        else:
            date_str = str(date_val).strip()
            
        if not date_str:
            stats["skipped_past"] += 1
            continue
            
        try:
            # Handle MM/DD/YYYY format from the sheet
            from dateutil import parser
            row_date = parser.parse(date_str).date()
            if row_date < today:
                stats["skipped_past"] += 1
                continue
        except Exception:
            # If we can't parse the date, assume it's past/invalid to be safe
            stats["skipped_past"] += 1
            continue
            
        # At this point, we have a valid, future/today reservation that isn't in the DB.
        try:
            # Map the Zapier row to the V2 Dashboard schema
            # We pass an empty dict for webhook_payload since we don't have one
            dashboard_row = map_legacy_to_dashboard(row, mpwr_id, {})
            
            # Tag it explicitly as a backfilled row
            dashboard_row["Trip Method"] = "BACKFILL"
            
            # Write to the V2 Dashboard
            success = write_dashboard_row(dashboard_row)
            if success:
                print(f"[SUCCESS] Migrated: {tw_conf} -> {mpwr_id} (Date: {date_str})")
                existing_tw_confs.add(tw_conf) # Prevent double insertion in same run
                stats["migrated"] += 1
                
                # Sleep to respect Google Sheets API Quota (100 req per 100 sec)
                # Since write_dashboard_row is 1 append_row call, 1 sec is safe
                time.sleep(1.0)
            else:
                print(f"[FAILED] Failed to write row for {tw_conf}")
                stats["errors"] += 1
                
        except Exception as e:
            print(f"[ERROR] Error migrating {tw_conf}: {e}")
            stats["errors"] += 1

    print("\n--- Backfill Complete ---")
    print(f"[SUCCESS] Migrated: {stats['migrated']}")
    print(f"[SKIP]  Already in DB: {stats['skipped_duplicate']}")
    print(f"[SKIP]  Past Date: {stats['skipped_past']}")
    print(f"[SKIP]  No MPWR ID/Error: {stats['skipped_no_mpwr']}")
    print(f"[FAILED] Errors: {stats['errors']}")
    
if __name__ == "__main__":
    # Ensure dependencies like dateutil are available for parsing random sheet dates
    try:
        import dateutil
    except ImportError:
        print("[Error] python-dateutil is not installed. Please run: pip install python-dateutil")
        sys.exit(1)
        
    run_backfill()
