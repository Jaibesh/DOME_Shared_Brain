import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Add shared to path
sys.path.append(str(Path(__file__).parent.parent))

from shared.supabase_client import get_supabase

def fix_corrupted_reservations():
    supabase = get_supabase()
    
    tw_confs = ["BZTF-EAMB", "HBMQ-CISK", "UVSE-BNVU"]
    
    print(f"Fixing data corruption for: {tw_confs}")
    
    # 1. Nullify mpwr_number in reservations table
    for conf in tw_confs:
        try:
            res = supabase.table("reservations").update({"mpwr_number": None}).eq("tw_confirmation", conf).execute()
            print(f"✅ Nullified mpwr_number in 'reservations' for {conf}: {len(res.data) if res.data else 0} rows affected")
        except Exception as e:
            print(f"❌ Error updating reservations for {conf}: {e}")
            
    # 2. Reset webhook status to 'pending' in pending_webhooks table
    # We want to find the creation webhooks (slug = 'booked') and set them to pending
    try:
        res = supabase.table("pending_webhooks").select("id, tw_confirmation, payload").in_("tw_confirmation", tw_confs).execute()
        webhooks = res.data or []
        
        for hook in webhooks:
            # Check if it's a creation webhook (booked)
            payload = hook.get("payload", {})
            slug = ""
            if "tripOrders" in payload and len(payload["tripOrders"]) > 0:
                slug = payload["tripOrders"][0].get("status", {}).get("slug", "")
                
            if slug == "booked":
                # Reset to pending
                update_res = supabase.table("pending_webhooks").update({"status": "pending"}).eq("id", hook["id"]).execute()
                print(f"✅ Reset webhook {hook['id']} (slug: {slug}) to 'pending' for {hook['tw_confirmation']}")
            else:
                print(f"ℹ️ Ignoring webhook {hook['id']} (slug: {slug}) for {hook['tw_confirmation']}")
                
    except Exception as e:
        print(f"❌ Error fetching/updating pending_webhooks: {e}")

if __name__ == "__main__":
    fix_corrupted_reservations()
