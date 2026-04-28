import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
s = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
r = s.table('reservations').select('tw_confirmation,guest_name,tw_booking_ids,activity_date').gte('activity_date','2026-04-27').execute()
empty = [x for x in r.data if not x.get('tw_booking_ids')]
print(f"Total upcoming: {len(r.data)}, Missing booking IDs: {len(empty)}")
for e in empty:
    conf = e["tw_confirmation"]
    name = e["guest_name"]
    date = e["activity_date"]
    print(f"  {conf} | {name} | {date}")
