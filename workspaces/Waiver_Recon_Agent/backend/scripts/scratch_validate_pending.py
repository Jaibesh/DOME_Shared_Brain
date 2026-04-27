"""Quick scan of pending Google Sheets rows for validation."""
import os, sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

from sheets import scan_for_pending_creations
from data_mapper import build_customer_payload_from_row

result = scan_for_pending_creations()
if not result or not result[0]:
    print('No pending creations or column not found')
else:
    col_idx, pending = result
    print(f'Column index for MPWR Conf: {col_idx}')
    print(f'Total pending rows: {len(pending)}')
    
    test_limit = min(10, len(pending))
    print(f'\nValidating first {test_limit} pending rows...\n')
    errors = 0
    for row in pending[:test_limit]:
        row_index = row['_row_index']
        payload = build_customer_payload_from_row(row, row_index)
        name = f"{row.get('First Name', '?')} {row.get('Last Name', '?')}"
        activity = str(row.get('Activity', '?'))[:50]
        
        if payload.get('error'):
            print(f'  Row {row_index}: FAIL - {name} | {activity}')
            print(f'    Error: {payload["error"]}')
            errors += 1
        else:
            print(f'  Row {row_index}: OK - {name}')
            print(f'    Activity: {payload["mpowr_activity"]}')
            print(f'    Vehicle: {payload["mpowr_vehicle"]} x{payload["vehicle_qty"]}')
            print(f'    Date: {payload["activity_date"]} {payload["activity_time"]}')
            print(f'    Price: ${payload["target_price"]:.2f}')
    
    print(f'\n{test_limit - errors}/{test_limit} pending rows validated OK')
    if errors:
        print(f'{errors} rows have data mapping errors')
