import sys
import os
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent')
from dotenv import load_dotenv
load_dotenv(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent\.env')
from supabase import create_client

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

res = supabase.table("reservations").select("*").eq("booking_type", "rental").execute()

from datetime import datetime, timedelta

count = 0
for row in res.data:
    time_str = row.get("activity_time", "")
    current_end = row.get("rental_return_time", "")
    tw_conf = row.get("tw_confirmation", "")
    
    # Check ticket_type or activity_name for duration
    ticket_type = row.get("ticket_type", "") or ""
    activity_name = row.get("activity_name", "") or ""
    act_internal = row.get("activity_internal", "") or ""
    
    combined = (ticket_type + " " + activity_name + " " + act_internal).lower()
    
    if not time_str or not tw_conf:
        continue
        
    hours = 0
    if "multi-day" in combined or "multi day" in combined:
        hours = -1 # Special marker for multi-day
    elif "24 hour" in combined or "24 hr" in combined:
        hours = 24
    elif "full-day" in combined or "full day" in combined:
        hours = 9
    elif "half-day" in combined or "half day" in combined:
        hours = 5
    elif "3 hour" in combined or "3 hr" in combined:
        hours = 3
    elif "2 hour" in combined or "2 hr" in combined:
        hours = 2
    elif "4 hour" in combined:
        hours = 4
        
    new_end = ""
    if hours > 0:
        try:
            start_dt = datetime.strptime(time_str.strip(), "%I:%M %p")
            end_dt = start_dt + timedelta(hours=hours)
            new_end = end_dt.strftime("%I:%M %p").lstrip("0")
        except Exception as e:
            print("Error parsing", time_str, e)
    elif hours == -1:
        new_end = "6:00 PM"
        
    if new_end and current_end != new_end:
        print(f"Updating {tw_conf} ({combined.strip()[:30]}): {time_str} -> {new_end} (was {current_end})")
        supabase.table("reservations").update({"rental_return_time": new_end, "end_time": new_end}).eq("tw_confirmation", tw_conf).execute()
        count += 1

print(f"Fixed {count} rentals.")
