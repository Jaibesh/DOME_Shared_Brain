import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(r'C:\DOME_CORE\workspaces\MPWR_Reservation_Agent\.env')
load_dotenv(env_path)
sys.path.append(r'C:\DOME_CORE')

from core.supabase_client import get_supabase
supabase = get_supabase()

tw_confs = ['BZTF-EAMB', 'HBMQ-CISK']
for conf in tw_confs:
    supabase.table('reservations').update({'mpwr_number': None}).eq('tw_confirmation', conf).execute()
    print(f"Nullified mpwr_number for {conf}")
    
    hooks = supabase.table('pending_webhooks').select('id, payload').eq('tw_confirmation', conf).execute()
    for hook in hooks.data or []:
        payload = hook.get('payload', {})
        slug = ''
        if 'tripOrders' in payload and len(payload['tripOrders']) > 0:
            slug = payload['tripOrders'][0].get('status', {}).get('slug', '')
        if slug == 'booked':
            supabase.table('pending_webhooks').update({'status': 'pending'}).eq('id', hook['id']).execute()
            print(f"Reset webhook {hook['id']} for {conf} to pending")
