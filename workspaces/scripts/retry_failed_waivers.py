import sys, os
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent')
from dotenv import load_dotenv
load_dotenv(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent\.env')
from supabase import create_client

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Reset all errored waiver webhooks to pending so the daemon reprocesses them
res = supabase.table("recon_webhooks").select("id, payload").eq("status", "error").execute()
count = 0
for w in res.data:
    supabase.table("recon_webhooks").update({"status": "pending", "error_message": None}).eq("id", w["id"]).execute()
    gn = w.get("payload", {}).get("full_name", "unknown")
    print(f"Reset {w['id']} ({gn}) to pending")
    count += 1

print(f"\nReset {count} failed webhooks to pending for reprocessing.")
