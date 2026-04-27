import os
import pytz
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from supabase_client import get_supabase
from supabase_data import _SHEET_TO_SUPABASE
import sheets

def _parse_time(time_str: str):
    if not time_str: return None
    time_str = time_str.strip()
    try:
        return datetime.strptime(time_str, "%I:%M %p").time()
    except ValueError:
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            return None

def _parse_date(date_str: str):
    if not date_str: return None
    date_part = date_str.split()[0]
    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_part, fmt).date()
        except ValueError:
            continue
    return None

def is_future(activity_date, activity_time):
    d = _parse_date(activity_date)
    t = _parse_time(activity_time)
    if not d: return False
    
    tz = pytz.timezone("America/Denver")
    now = datetime.now(tz)
    
    if t:
        dt = tz.localize(datetime.combine(d, t))
    else:
        # If no time, assume end of day
        dt = tz.localize(datetime.combine(d, datetime.max.time()))
        
    return dt > now

def map_to_supabase(sheet_row):
    sb_row = {}
    for sheet_col, sb_col in _SHEET_TO_SUPABASE.items():
        val = sheet_row.get(sheet_col)
        
        if sb_col in ['epic_expected', 'epic_complete', 'polaris_expected', 'polaris_complete', 'ohv_expected', 'ohv_complete', 'party_size', 'vehicle_qty']:
            try:
                sb_row[sb_col] = int(val) if val else 0
            except ValueError:
                sb_row[sb_col] = 0
        elif sb_col in ['amount_due', 'amount_paid']:
            try:
                clean_val = str(val).replace('$', '').replace(',', '')
                sb_row[sb_col] = float(clean_val) if clean_val else 0.0
            except ValueError:
                sb_row[sb_col] = 0.0
        elif sb_col in ['ohv_required', 'ohv_uploaded', 'checked_in']:
            sb_row[sb_col] = str(val).strip().upper() == "TRUE"
        elif sb_col in ['epic_names', 'polaris_names', 'ohv_permit_names']:
            sb_row[sb_col] = [x.strip() for x in str(val).split(',')] if val else []
        elif sb_col in ['created_at', 'last_updated', 'checked_in_at']:
            sb_row[sb_col] = str(val) if val else None
        else:
            # Empty strings should be empty strings, not None for most text columns
            sb_row[sb_col] = str(val) if val is not None else ""
            
    # guest_name
    first = str(sheet_row.get("First Name", "")).strip()
    last = str(sheet_row.get("Last Name", "")).strip()
    sb_row["guest_name"] = f"{first} {last}".strip()
    
    if not sb_row["guest_name"]:
        sb_row["guest_name"] = str(sheet_row.get("Guest Name", "")).strip()
        
    # Ensure TW Confirmation
    if not sb_row.get("tw_confirmation"):
        sb_row["tw_confirmation"] = str(sheet_row.get("Confirmation Code", "")).strip()
        
    # Default booking type if empty
    if not sb_row.get("booking_type"):
        if "rental" in str(sheet_row.get("Activity", "")).lower():
            sb_row["booking_type"] = "Rental"
        else:
            sb_row["booking_type"] = "Tour"
            
    return sb_row

def main():
    supabase = get_supabase()
    client = sheets._get_client()
    if not client:
        print("Failed to init sheets client")
        return
        
    print("Fetching V2 Dashboard records...")
    dash_sheet_id = os.getenv("DASHBOARD_SHEET_ID")
    dash_records = client.open_by_key(dash_sheet_id).sheet1.get_all_records()
    print(f"Total V2 records: {len(dash_records)}")
    
    processed_tws = set()
    to_insert = []
    
    for row in dash_records:
        tw = str(row.get("TW Confirmation", "")).strip().upper()
        if not tw: continue
        
        adate = str(row.get("Activity Date", ""))
        atime = str(row.get("Activity Time", ""))
        
        if is_future(adate, atime):
            processed_tws.add(tw)
            to_insert.append(map_to_supabase(row))
            
    print(f"Found {len(to_insert)} future records from V2.")
    
    def chunker(seq, size):
        return (seq[pos:pos + size] for pos in range(0, len(seq), size))
        
    for chunk in chunker(to_insert, 100):
        try:
            supabase.table("reservations").insert(chunk).execute()
        except Exception as e:
            print(f"Error inserting V2 chunk: {e}")
            
    print("V2 records inserted.")
    
    print("Fetching Original Zapier records...")
    zapier_sheet_id = "10DIqgwuWgTsi69ObujEOaBbdPz-HHRbzn9mCw2cEc4g"
    try:
        zap_records = client.open_by_key(zapier_sheet_id).sheet1.get_all_records()
    except Exception as e:
        print(f"Failed to open Zapier sheet: {e}")
        return
        
    to_insert_zap = []
    for row in zap_records:
        tw = str(row.get("TW Confirmation", "") or row.get("Confirmation Code", "")).strip().upper()
        if not tw: continue
        if tw in processed_tws: continue
        
        adate = str(row.get("Activity Date", ""))
        atime = str(row.get("Activity Time", "") or row.get("Start Time", ""))
        
        if is_future(adate, atime):
            processed_tws.add(tw)
            sb_row = map_to_supabase(row)
            # Need to fix tw_confirmation explicitly since Zapier sheet uses 'Confirmation Code' sometimes
            sb_row["tw_confirmation"] = tw
            to_insert_zap.append(sb_row)
            
    print(f"Found {len(to_insert_zap)} additional future records from Zapier sheet.")
    
    for chunk in chunker(to_insert_zap, 100):
        try:
            supabase.table("reservations").insert(chunk).execute()
        except Exception as e:
            print(f"Error inserting Zapier chunk: {e}")
            
    print("Zapier records inserted. Recovery complete.")

if __name__ == "__main__":
    main()
