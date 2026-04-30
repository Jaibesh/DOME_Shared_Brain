import sys
import os
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent')
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Get all future rentals
res = supabase.table("reservations").select("*").eq("Booking Type", "rental").neq("MPWR Status", "Cancelled").execute()

from datetime import datetime, timedelta
import re

count = 0
for row in res.data:
    act = row.get("Activity Internal", "")
    time_str = row.get("Activity Time", "")
    current_end = row.get("Rental Return Time", "")
    
    if not act or not time_str:
        continue
        
    match = re.search(r'(\d+)\.0 Hrs', act)
    new_end = ""
    if match:
        hours = int(match.group(1))
        if hours > 0:
            try:
                start_dt = datetime.strptime(time_str.strip(), "%I:%M %p")
                end_dt = start_dt + timedelta(hours=hours)
                new_end = end_dt.strftime("%I:%M %p").lstrip("0")
            except Exception as e:
                print("Error parsing", time_str, e)
    elif "multi" in act.lower():
        new_end = "5:00 PM"
        
    if new_end and current_end != new_end:
        print(f"Updating {row.get('First Name')} ({act}): {time_str} -> {new_end} (was {current_end})")
        supabase.table("reservations").update({"Rental Return Time": new_end, "End Time": new_end}).eq("id", row["id"]).execute()
        count += 1

print(f"Fixed {count} rentals.")
