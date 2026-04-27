import os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Waiver_Dashboard', 'backend', '.env'))
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

print("Resetting failed waivers to pending...")
res = sb.table("recon_webhooks").update({"status": "pending"}).eq("status", "error").execute()
print(f"Reset {len(res.data or [])} failed waivers!")
