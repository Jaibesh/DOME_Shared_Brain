import os
import time
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

def handle_insert(payload):
    print("New webhook inserted!", payload)

print("Subscribing to pending_webhooks...")
try:
    # Supabase-py realtime syntax
    supabase.table("pending_webhooks").on("INSERT", handle_insert).subscribe()
    print("Subscribed! Waiting 15 seconds...")
    time.sleep(15)
except Exception as e:
    print(f"Error: {e}")
