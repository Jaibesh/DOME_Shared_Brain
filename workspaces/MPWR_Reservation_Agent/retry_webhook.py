"""Quick utility to reset a webhook in Supabase back to 'pending' for retry."""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

tw_conf = sys.argv[1] if len(sys.argv) > 1 else "AIRK-WWMB"

# Check current status
res = supabase.table("pending_webhooks").select("id, tw_confirmation, status, created_at").eq("tw_confirmation", tw_conf).execute()

if not res.data:
    print(f"No webhooks found for {tw_conf}")
    sys.exit(1)

for row in res.data:
    print(f"  ID: {row['id']}  Status: {row['status']}  Created: {row['created_at']}")

# Reset the most recent one back to pending
latest = res.data[-1]
if latest["status"] == "pending":
    print(f"\n✅ Already pending — the agent will pick it up on the next cycle.")
elif latest["status"] == "retry":
    print(f"\n✅ Already in retry — the agent will pick it up on the next cycle.")
else:
    supabase.table("pending_webhooks").update({"status": "pending"}).eq("id", latest["id"]).execute()
    print(f"\n✅ Reset webhook {latest['id']} from '{latest['status']}' → 'pending'")
    print(f"   The agent will pick up {tw_conf} on the next polling cycle.")
