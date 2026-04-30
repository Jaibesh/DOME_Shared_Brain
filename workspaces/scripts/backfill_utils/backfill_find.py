"""
Backfill tw_customer_portal_url for all existing reservations.
Runs in the browser console via fetch() using the active TripWorks session.

Step 1: Get all reservations missing tw_customer_portal_url from Supabase
Step 2: For each, hit TripWorks API to get the customer_portal_hash
Step 3: Build the portal URL and update Supabase + generate QR code
"""
import os, sys, json, time
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(r'C:\DOME_CORE\workspaces\Waiver_Recon_Agent\.env'))
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Get all reservations that need backfilling
res = sb.table('reservations').select(
    'tw_confirmation, tw_customer_portal_url, activity_date'
).gte('activity_date', '2026-04-01').order('activity_date', desc=False).execute()

need_backfill = []
already_done = 0
for row in (res.data or []):
    tw_conf = row.get('tw_confirmation', '')
    portal = row.get('tw_customer_portal_url', '')
    if not tw_conf:
        continue
    if portal and portal.strip():
        already_done += 1
        continue
    need_backfill.append(tw_conf)

print(f"Total reservations from Apr 1+: {len(res.data or [])}")
print(f"Already have portal URL: {already_done}")
print(f"Need backfill: {len(need_backfill)}")
print()

# Output the list as a JSON array for the browser script to use
output_path = r'C:\DOME_CORE\backfill_confs.json'
with open(output_path, 'w') as f:
    json.dump(need_backfill, f)
print(f"Saved {len(need_backfill)} confirmation codes to {output_path}")
print(f"\nConfirmation codes: {need_backfill}")
