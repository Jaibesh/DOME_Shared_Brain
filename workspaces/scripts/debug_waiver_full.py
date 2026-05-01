import sys, os, json
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent')
from dotenv import load_dotenv
load_dotenv(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent\.env')
from supabase import create_client

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Dump full payloads for these errors to see ALL available fields
r = supabase.table("recon_webhooks").select("*").eq("status", "error").execute()
for w in r.data:
    payload = w.get("payload", {})
    gn = payload.get("full_name", "")
    if "Johnson" in gn:
        print("=== FULL PAYLOAD for Matthew Johnson ===")
        print(json.dumps(payload, indent=2, default=str))
        break
