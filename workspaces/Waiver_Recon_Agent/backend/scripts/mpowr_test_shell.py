import json
from scraper import scrape_mpowr_reservations
from dotenv import load_dotenv
import os

def run_test():
    load_dotenv()
    
    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")
    
    print(f"Starting MPOWR Scraper Test for email: {email}")
    print("This will launch a headless browser and extract current reservations.")
    
    if not password or "your_super_secret" in password:
        print("ERROR: Please update MPOWR_PASSWORD in the .env file with your actual password.")
        return
        
    try:
        results = scrape_mpowr_reservations(email, password)
        print("\n\n--- RESULTS SUCCESSFUL MINING ---")
        print(json.dumps(results, indent=2))
        print("---------------------------------")
        print(f"Extracted {len(results)} total reservations.")
    except Exception as e:
        import traceback
        print(f"\nERROR OCCURRED DURING MINING:")
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
