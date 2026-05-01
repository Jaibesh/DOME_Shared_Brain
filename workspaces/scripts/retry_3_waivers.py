import sys, os
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent')
from dotenv import load_dotenv
load_dotenv(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent\.env')
from supabase import create_client

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

ids = [
    "082d319b-c6f6-49ff-94ad-7cf2269aaa23",  # Matthew Johnson
    "8e45c06f-40b7-4d4d-9175-e3544263c6e0",  # Daniel Wegh
    "69d9963b-707f-4120-82a9-21767b037a3e",  # Patricia Wegh
]

for wid in ids:
    supabase.table("recon_webhooks").update({"status": "pending", "error_message": None}).eq("id", wid).execute()
    print(f"Reset {wid} to pending")

print("Done.")
