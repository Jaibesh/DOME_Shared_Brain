import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
s = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Check all errored waiver webhooks 
r = s.table('recon_webhooks').select('id,payload,error_message').eq('status','error').execute()
print(f"{len(r.data)} errored waiver webhooks\n")

for x in r.data:
    rec_id = x['id'][:8]
    p = x['payload']
    name = p.get('full_name', '?')
    bookings = p.get('bookings', [])
    booking_id = bookings[0].get('id', '?') if bookings else '?'
    err = x.get('error_message', '')[:80]
    print(f"  {rec_id} | {name} | booking_id={booking_id} | {err}")
