import os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Waiver_Dashboard', 'backend', '.env'))
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

print("=== Checking for Status Logs ===")
res = sb.table('pending_webhooks').select('tw_confirmation, created_at, payload').like('tw_confirmation', 'LOG_STATUS_%').order('created_at', desc=True).limit(5).execute()

if res.data:
    for row in res.data:
        print(f"\n--- Log Entry: {row['tw_confirmation']} @ {row['created_at']} ---")
        payload = row['payload']
        print(f"Status: {payload.get('status')}")
        print(f"Customer: {payload.get('customer', {}).get('full_name')}")
        
        trip_order = payload.get("trip_order", {})
        experience = trip_order.get("experience", {}).get("name", "NONE")
        timeslot = trip_order.get("experience_timeslot", {}).get("start_time", "NONE")
        print(f"Experience: {experience}")
        print(f"Timeslot: {timeslot}")
        print("Raw payload dump:")
        print(json.dumps(payload, indent=2))
else:
    print("NO LOGS FOUND. The webhook NEVER HIT tw-status-changed.")
    
print("\n=== Checking update_webhooks queue for Wade Pilling ===")
res2 = sb.table('update_webhooks').select('tw_confirmation, created_at').eq('tw_confirmation', 'RNFC-BDXB').order('created_at', desc=True).limit(3).execute()
for r in res2.data or []:
    print(r)
