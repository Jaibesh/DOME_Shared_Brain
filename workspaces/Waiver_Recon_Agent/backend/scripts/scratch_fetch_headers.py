import json
from sheets import fetch_database

data = fetch_database()
if data:
    print(json.dumps(list(data[0].keys()), indent=2))
else:
    print("No data found or auth failed.")
