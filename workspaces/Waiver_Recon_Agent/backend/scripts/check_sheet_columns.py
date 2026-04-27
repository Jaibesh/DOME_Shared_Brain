import sys
import os
import re

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")
from sheets import get_sheets_client

client = get_sheets_client()
sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_ID")).sheet1
records = sheet.get_all_records(value_render_option="FORMATTED_VALUE")

if len(records) > 0:
    print("Columns:", list(records[0].keys()))

for r in records:
    if "Multi-Day" in str(r.get("Activity", "")) or "Multi-Day" in str(r.get("Ticket Type", "")):
        print(f"Row {r.get('First Name')} - Activity: {r.get('Activity')}")
        for k, v in r.items():
            if str(v).strip():
                print(f"  {k}: {v}")
        break
