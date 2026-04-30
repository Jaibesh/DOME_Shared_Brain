"""
Backfill tw_customer_portal_url — Non-interactive version.
Uses Playwright with stored auth state to avoid login prompts.
"""
import json, os, sys, time
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(r'C:\DOME_CORE\workspaces\Waiver_Recon_Agent\.env'))
from supabase import create_client
from playwright.sync_api import sync_playwright

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Load confirmation codes
with open(r'C:\DOME_CORE\backfill_confs.json') as f:
    all_confs = json.load(f)

print(f"Total to backfill: {len(all_confs)}")

# Use the MPOWR browser login flow which handles TripWorks SSO
sys.path.insert(0, r'C:\DOME_CORE\workspaces\shared')

def do_backfill():
    found = 0
    errors = 0
    skipped = 0
    results = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Go directly to TripWorks - try loading the manifest first
        print("[1] Loading TripWorks...")
        page.goto("https://epic4x4.tripworks.com/manifest/TableView/2026-04-30/default", timeout=30000)
        time.sleep(2)
        
        # Check if we're on TripWorks (not redirected to login)
        current_url = page.url
        print(f"[2] Current URL: {current_url}")
        
        if "login" in current_url.lower() or "signin" in current_url.lower() or "accounts.google" in current_url.lower():
            print("[!] Need to log in. Will wait 60 seconds for manual login...")
            # Instead of input(), just wait and keep checking
            for i in range(60):
                time.sleep(1)
                if "tripworks.com/manifest" in page.url or "tripworks.com/trip" in page.url:
                    print(f"[OK] Login detected after {i+1}s")
                    break
            else:
                print("[X] Login timeout. Trying to continue anyway...")
        
        # Test with one request first
        print("[3] Testing API access...")
        test_result = page.evaluate('''
            async () => {
                try {
                    const r = await fetch("/api/trip/ZCIX-NSZF/get", {
                        headers: {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
                        credentials: "include"
                    });
                    if (!r.ok) return {error: "HTTP " + r.status};
                    const d = await r.json();
                    const h = (d.trip && d.trip.customer_portal_hash) || d.customer_portal_hash;
                    return {hash: h, ok: true};
                } catch(e) {
                    return {error: e.message};
                }
            }
        ''')
        
        if not test_result or test_result.get('error'):
            print(f"[X] API test failed: {test_result}")
            browser.close()
            return {}
        
        print(f"[OK] API test passed. Hash: {test_result.get('hash', 'N/A')[:20]}...")
        
        # Process all confirmations
        print(f"[4] Fetching portal URLs for {len(all_confs)} reservations...")
        
        for i, conf in enumerate(all_confs):
            try:
                resp = page.evaluate(f'''
                    async () => {{
                        try {{
                            const r = await fetch("/api/trip/{conf}/get", {{
                                headers: {{"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}},
                                credentials: "include"
                            }});
                            if (!r.ok) return {{error: r.status}};
                            const d = await r.json();
                            const h = (d.trip && d.trip.customer_portal_hash) || d.customer_portal_hash;
                            return {{hash: h}};
                        }} catch(e) {{
                            return {{error: e.message}};
                        }}
                    }}
                ''')
                
                if resp and resp.get('hash'):
                    portal_url = f"https://epic4x4.tripworks.com/customerPortal/{resp['hash']}/index"
                    results[conf] = portal_url
                    found += 1
                elif resp and resp.get('error') == 404:
                    skipped += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
            
            # Progress every 50
            if (i + 1) % 50 == 0:
                print(f"  Progress: {i+1}/{len(all_confs)} — found {found}, errors {errors}, skipped {skipped}")
            
            # Small delay every 20 to avoid rate limiting
            if (i + 1) % 20 == 0:
                time.sleep(0.3)
        
        browser.close()
    
    # Save results
    results_path = r'C:\DOME_CORE\backfill_results.json'
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[DONE] Found {found} portal URLs, {errors} errors, {skipped} skipped (404)")
    print(f"Results saved to {results_path}")
    
    return results

def update_supabase(results):
    print(f"\nUpdating {len(results)} reservations in Supabase...")
    updated = 0
    for conf, url in results.items():
        try:
            sb.table('reservations').update({
                'tw_customer_portal_url': url
            }).eq('tw_confirmation', conf.upper()).execute()
            updated += 1
        except Exception as e:
            print(f"  [{conf}] DB update failed: {e}")
        if updated % 100 == 0 and updated > 0:
            print(f"  DB Progress: {updated}/{len(results)}")
    print(f"DB Updated: {updated}/{len(results)}")

def generate_qr_codes(results):
    import qrcode
    import io
    
    print(f"\nGenerating QR codes for {len(results)} portal URLs...")
    generated = 0
    
    for conf, url in results.items():
        try:
            qr = qrcode.make(url)
            buffer = io.BytesIO()
            qr.save(buffer, format="PNG")
            buffer.seek(0)
            
            qr_file_path = f"portal_{conf}.png"
            try:
                sb.storage.from_("waiver-qr-codes").remove([qr_file_path])
            except:
                pass
            sb.storage.from_("waiver-qr-codes").upload(
                path=qr_file_path,
                file=buffer.getvalue(),
                file_options={"content-type": "image/png", "upsert": "true"},
            )
            qr_public_url = sb.storage.from_("waiver-qr-codes").get_public_url(qr_file_path)
            
            sb.table('reservations').update({
                'tw_customer_portal_qr_url': qr_public_url,
            }).eq('tw_confirmation', conf.upper()).execute()
            
            generated += 1
            if generated % 50 == 0:
                print(f"  QR Progress: {generated}/{len(results)}")
        except Exception as e:
            print(f"  [{conf}] QR failed: {e}")
    
    print(f"QR Generated: {generated}/{len(results)}")

if __name__ == "__main__":
    # Check if we already have results
    results_path = r'C:\DOME_CORE\backfill_results.json'
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)
        print(f"Loaded {len(results)} existing results from cache")
        if len(results) < 100:
            print("Too few results — re-running backfill...")
            results = do_backfill()
    else:
        results = do_backfill()
    
    if not results:
        print("No results. Exiting.")
        sys.exit(1)
    
    update_supabase(results)
    generate_qr_codes(results)
    print("\n[OK] Backfill complete!")
