"""
diagnose_webhooks.py -- Check all webhook tables for recent activity
"""
import os
import sys
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Waiver_Dashboard', 'backend', '.env'))

from supabase import create_client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
sb = create_client(url, key)

print("=" * 70)
print("  TripWorks Webhook Diagnostic Report")
print(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Check all webhook tables
tables = [
    ("pending_webhooks", "MPWR New Reservation Webhooks"),
    ("update_webhooks", "MPWR Update Webhooks"),
    ("cancel_webhooks", "MPWR Cancel Webhooks"),
    ("recon_webhooks", "Waiver Completed Webhooks"),
]

for table_name, label in tables:
    print(f"\n{'-' * 70}")
    print(f"[TABLE] {label} ({table_name})")
    print(f"{'-' * 70}")
    
    try:
        # Total count
        all_res = sb.table(table_name).select("id", count="exact").execute()
        total = all_res.count if hasattr(all_res, 'count') and all_res.count is not None else len(all_res.data or [])
        
        # Get most recent 5
        recent = sb.table(table_name).select("*").order("created_at", desc=True).limit(5).execute()
        records = recent.data or []
        
        # Status breakdown
        for status in ["pending", "processed", "retry", "failed"]:
            status_res = sb.table(table_name).select("id", count="exact").eq("status", status).execute()
            count = status_res.count if hasattr(status_res, 'count') and status_res.count is not None else len(status_res.data or [])
            if count > 0:
                print(f"  {status.upper():12s}: {count}")
        
        print(f"  {'TOTAL':12s}: {total}")
        
        if records:
            print(f"\n  Most recent {len(records)} entries:")
            for r in records:
                created = r.get("created_at", "?")
                status = r.get("status", "?")
                tw_conf = r.get("tw_confirmation", "?")
                wh_type = r.get("webhook_type", "")
                print(f"    [{created}] Status={status}, TW={tw_conf}" + (f", Type={wh_type}" if wh_type else ""))
        else:
            print("\n  ** NO RECORDS FOUND IN THIS TABLE **")
            
    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "does not exist" in error_str.lower() or "relation" in error_str.lower():
            print(f"  ** TABLE DOES NOT EXIST -- needs to be created in Supabase **")
        else:
            print(f"  [ERROR] querying table: {e}")

print(f"\n{'=' * 70}")
print("  Diagnosis Summary")
print(f"{'=' * 70}")
print("""
If tables are EMPTY or DON'T EXIST, TripWorks webhooks are NOT reaching
the Dashboard backend. Common causes:

  1. TripWorks webhook URLs are not configured (or misconfigured)
     → Need to set them in TripWorks admin to point at your Railway URL
     → Expected endpoints:
       POST https://<your-railway-domain>/api/webhook/tw-mpwr-update
       POST https://<your-railway-domain>/api/webhook/tw-mpwr-cancel  
       POST https://<your-railway-domain>/api/webhook/tw-waiver-complete

  2. Railway backend is DOWN or has crashed
     → Check Railway dashboard for service status and logs

  3. TripWorks webhook events are not enabled
     → Check TripWorks admin > Webhooks > ensure 'trip.updated', 
       'trip.canceled', and 'waiver.completed' events are toggled ON

  4. Firewall or SSL issues between TripWorks and Railway
""")
