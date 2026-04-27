import json
import urllib.parse
from pprint import pprint

try:
    with open('mpowr_network.har', 'r', encoding='utf-8', errors='ignore') as f:
        har = json.load(f)
        
    entries = har.get('log', {}).get('entries', [])
    found = False
    for e in entries:
        req = e.get('request', {})
        url = req.get('url', '')
        if 'orders/create.data' in url and req.get('method') == 'POST':
            post_data = req.get('postData', {})
            text = post_data.get('text', '')
            if text:
                parsed = urllib.parse.parse_qs(text)
                
                print("==================================")
                print("FOUND MPOWR RESERVATION PAYLOAD:")
                print(f"URL: {url}")
                print("==================================")
                
                # Simplify output
                for key, val in parsed.items():
                    print(f"'{key}': {val}")
                found = True
                
    if not found:
        print("No valid POST payload to create.data found.")
except Exception as ex:
    print(f"Error parsing HAR: {ex}")
