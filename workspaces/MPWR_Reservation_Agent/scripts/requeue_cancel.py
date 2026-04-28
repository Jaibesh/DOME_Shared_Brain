"""Re-queue the DJCX-JPSE cancel webhook."""
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

webhook_id = "31661dae-fa58-40f3-b7a7-31959044edcb"

# Verify it's the right one
res = sb.table("cancel_webhooks").select("id,status,payload").eq("id", webhook_id).execute()
row = res.data[0]
conf = row["payload"].get("confirmation_code", "")
print(f"Webhook ID: {row['id']}")
print(f"Confirmation: {conf}")
print(f"Current status: {row['status']}")

# Reset to pending
sb.table("cancel_webhooks").update({"status": "pending", "retry_count": 0}).eq("id", webhook_id).execute()
print("-> Reset to 'pending'! The bot will pick it up on next poll cycle.")
