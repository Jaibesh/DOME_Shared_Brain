"""
supabase_data.py — Supabase Data Layer for the Dashboard

Native snake_case implementation.
"""

import os
import re
from datetime import datetime, date, timedelta

import pytz
from dotenv import load_dotenv

from supabase_client import get_supabase

load_dotenv()

MDT = pytz.timezone("America/Denver")

def _parse_date(date_str: str) -> date | None:
    if not date_str:
        return None
    cleaned = date_str.strip()
    cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', cleaned, flags=re.IGNORECASE)
    date_part = cleaned.split()[0] if '/' in cleaned or '-' in cleaned.split()[0] else cleaned
    
    for fmt in [
        "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y",
        "%m-%d-%Y", "%m-%d-%y",
        "%b %d, %Y", "%B %d, %Y",
    ]:
        try:
            parse_target = date_part if '/' in date_part or (len(date_part) <= 10 and '-' in date_part) else cleaned
            return datetime.strptime(parse_target, fmt).date()
        except ValueError:
            continue
    return None

def fetch_all_records() -> list[dict]:
    try:
        supabase = get_supabase()
        res = supabase.table("reservations").select("*").execute()
        return res.data or []
    except Exception as e:
        print(f"[SupabaseData] Error fetching all records: {e}")
        return []

def fetch_todays_arrivals() -> list[dict]:
    try:
        supabase = get_supabase()
        today = datetime.now(MDT).date()
        today_iso = today.isoformat()
        
        res = supabase.table("reservations").select("*").eq("activity_date", today_iso).execute()
        rows = res.data or []
        
        # Also include active rentals from the recent past (up to 7 days back)
        # that haven't been returned yet. The .gte filter strictly enforces
        # that NO ghost rentals older than 7 days will ever appear.
        floor_date_obj = today - timedelta(days=7)
        floor_date = floor_date_obj.isoformat()
        rental_res = supabase.table("reservations") \
            .select("*") \
            .eq("booking_type", "Rental") \
            .lt("activity_date", today_iso) \
            .gte("activity_date", floor_date) \
            .execute()
        
        for r in (rental_res.data or []):
            rs = str(r.get("rental_status", "")).strip().lower()
            if rs not in ("returned", "completed", ""):
                if r.get("tw_confirmation") not in [x.get("tw_confirmation") for x in rows]:
                    rows.append(r)
        
        seen = set()
        unique = []
        for r in rows:
            tc = r.get("tw_confirmation", "")
            if tc and tc not in seen:
                seen.add(tc)
                unique.append(r)
        
        return unique
    except Exception as e:
        print(f"[SupabaseData] Error fetching today's arrivals: {e}")
        return []

def fetch_by_tw_conf(tw_conf: str) -> dict | None:
    try:
        supabase = get_supabase()
        res = supabase.table("reservations").select("*").eq("tw_confirmation", tw_conf.strip().upper()).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        print(f"[SupabaseData] Error fetching {tw_conf}: {e}")
        return None

def update_field(tw_conf: str, sb_col: str, value) -> bool:
    try:
        supabase = get_supabase()
        updates = {
            sb_col: value,
            "last_updated": datetime.now(MDT).isoformat()
        }
        res = supabase.table("reservations").update(updates).eq("tw_confirmation", tw_conf).execute()
        return len(res.data or []) > 0
    except Exception as e:
        print(f"[SupabaseData] Error updating {tw_conf}.{sb_col}: {e}")
        return False

def update_multiple_fields(tw_conf: str, updates: dict) -> bool:
    try:
        supabase = get_supabase()
        updates["last_updated"] = datetime.now(MDT).isoformat()
        
        # Ensure timestamp strings are not empty
        for k in ['created_at', 'last_updated', 'checked_in_at']:
            if k in updates and updates[k] == "":
                updates[k] = None
                
        res = supabase.table("reservations").update(updates).eq("tw_confirmation", tw_conf).execute()
        return len(res.data or []) > 0
    except Exception as e:
        print(f"[SupabaseData] Error updating {tw_conf}: {e}")
        return False

def increment_waiver_count(tw_conf: str, waiver_type: str, signer_name: str) -> bool:
    try:
        supabase = get_supabase()
        res = supabase.table("reservations").select("*").eq("tw_confirmation", tw_conf).execute()
        if not res.data:
            return False
        
        row = res.data[0]
        count_col = f"{waiver_type}_complete"
        names_col = f"{waiver_type}_names"
        
        current_count = row.get(count_col, 0) or 0
        current_names = row.get(names_col, []) or []
        
        clean_name = re.sub(r'\s*\(\d+.*?\)\s*$', '', signer_name).strip().lower()
        existing_clean = [re.sub(r'\s*\(\d+.*?\)\s*$', '', n).strip().lower() for n in current_names]
        
        if clean_name in existing_clean:
            return True
        
        new_names = current_names + [signer_name]
        updates = {
            count_col: current_count + 1,
            names_col: new_names,
            "last_updated": datetime.now(MDT).isoformat()
        }
        
        supabase.table("reservations").update(updates).eq("tw_confirmation", tw_conf).execute()
        return True
    except Exception as e:
        print(f"[SupabaseData] Error incrementing waiver: {e}")
        return False

def fetch_upcoming_reservations(limit=30):
    """Fetch the next N future reservations by date+time, looking into future days.
    Used to always fill the UPCOMING section even at end of day."""
    try:
        supabase = get_supabase()
        today_iso = datetime.now(MDT).date().isoformat()
        
        # Fetch more than needed to account for filtering out checked-in guests
        res = supabase.table("reservations") \
            .select("*") \
            .gte("activity_date", today_iso) \
            .order("activity_date", desc=False) \
            .order("activity_time", desc=False) \
            .limit(limit + 50) \
            .execute()
        return res.data or []
    except Exception as e:
        print(f"[SupabaseData] Error fetching upcoming reservations: {e}")
        return []

