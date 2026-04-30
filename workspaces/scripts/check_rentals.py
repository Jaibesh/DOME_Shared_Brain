import sys
import os
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent')
from dotenv import load_dotenv
load_dotenv(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent\.env')
from supabase import create_client

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

res = supabase.table("reservations").select("*").eq("booking_type", "rental").execute()
for row in res.data:
    print(row.get("tw_confirmation"), row.get("activity_internal"), row.get("rental_return_time"), row.get("activity_time"), row.get("ticket_type"))
