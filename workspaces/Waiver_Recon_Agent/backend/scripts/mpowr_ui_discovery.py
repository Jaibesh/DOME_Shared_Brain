"""
mpowr_ui_discovery.py — One-Time Form Selector Mapping Tool

Launches a headed Playwright browser, logs into MPOWR, navigates to /orders/create,
and dumps every interactive form element (inputs, selects, buttons, dropdowns)
to mpowr_form_selectors.json.

Run this ONCE with the user watching to confirm selectors are correct.
After confirming, the output feeds into mpowr_creator_bot.py.

Usage:
    python mpowr_ui_discovery.py
"""

import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from mpowr_login import login_to_mpowr

load_dotenv()

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mpowr_form_selectors.json")


def capture_form_elements(page) -> dict:
    """Extract all interactive form elements from the current page."""

    inputs = page.eval_on_selector_all(
        'input, select, textarea',
        """els => els.map(e => ({
            tag: e.tagName.toLowerCase(),
            name: e.name || null,
            id: e.id || null,
            type: e.type || null,
            placeholder: e.placeholder || null,
            ariaLabel: e.getAttribute('aria-label') || null,
            classes: e.className || null,
            value: e.value || null,
            required: e.required || false,
            disabled: e.disabled || false,
            options: e.tagName === 'SELECT'
                ? Array.from(e.options).map(o => ({value: o.value, text: o.text, selected: o.selected}))
                : null
        }))"""
    )

    buttons = page.eval_on_selector_all(
        'button, [role="button"], input[type="submit"]',
        """els => els.map(e => ({
            tag: e.tagName.toLowerCase(),
            text: e.textContent ? e.textContent.trim().substring(0, 100) : null,
            type: e.type || null,
            id: e.id || null,
            classes: e.className || null,
            disabled: e.disabled || false,
            ariaLabel: e.getAttribute('aria-label') || null,
        }))"""
    )

    # Look for custom dropdown/combobox components (React Select, etc.)
    custom_dropdowns = page.eval_on_selector_all(
        '[class*="select"], [class*="dropdown"], [class*="combobox"], [role="listbox"], [role="combobox"]',
        """els => els.map(e => ({
            tag: e.tagName.toLowerCase(),
            classes: e.className || null,
            role: e.getAttribute('role') || null,
            ariaLabel: e.getAttribute('aria-label') || null,
            text: e.textContent ? e.textContent.trim().substring(0, 200) : null,
            id: e.id || null,
        }))"""
    )

    # Look for date picker elements
    date_elements = page.eval_on_selector_all(
        '[class*="date"], [class*="calendar"], [class*="picker"], input[type="date"], input[type="datetime"]',
        """els => els.map(e => ({
            tag: e.tagName.toLowerCase(),
            classes: e.className || null,
            type: e.type || null,
            id: e.id || null,
            name: e.name || null,
            ariaLabel: e.getAttribute('aria-label') || null,
        }))"""
    )

    return {
        "inputs": inputs,
        "buttons": buttons,
        "custom_dropdowns": custom_dropdowns,
        "date_elements": date_elements,
    }


def run_discovery():
    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")

    if not email or not password:
        print("ERROR: MPOWR_EMAIL or MPOWR_PASSWORD not set in .env")
        return

    print("=" * 60)
    print("MPOWR UI DISCOVERY TOOL")
    print("=" * 60)
    print("This tool will log into MPOWR and map the create-order form.")
    print("Watch the browser to confirm everything looks correct.")
    print()

    results = {
        "discovered_at": datetime.now().isoformat(),
        "url": "https://mpwr-hq.poladv.com/orders/create",
        "states": {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Step 1: Login
        print("\n[1/6] Logging in to MPOWR...")
        try:
            login_to_mpowr(page, email, password)
        except Exception as e:
            print(f"Login failed: {e}")
            print("Please log in manually in the browser window.")
            input("Press Enter when logged in...")

        # Step 2: Navigate to create page
        print("\n[2/6] Navigating to /orders/create...")
        page.goto("https://mpwr-hq.poladv.com/orders/create", wait_until="domcontentloaded")
        time.sleep(5)

        # Screenshot: Empty form
        ss_path = os.path.join(SCREENSHOT_DIR, "discovery_01_empty_form.png")
        page.screenshot(path=ss_path, full_page=True)
        print(f"  Screenshot saved: {ss_path}")

        # Capture form elements in initial state
        print("\n[3/6] Capturing form elements (initial state)...")
        results["states"]["initial"] = capture_form_elements(page)
        print(f"  Found {len(results['states']['initial']['inputs'])} inputs")
        print(f"  Found {len(results['states']['initial']['buttons'])} buttons")
        print(f"  Found {len(results['states']['initial']['custom_dropdowns'])} custom dropdowns")
        print(f"  Found {len(results['states']['initial']['date_elements'])} date elements")

        # Step 3: Explore the page structure
        print("\n[4/6] Capturing full page HTML structure...")
        # Get the outer HTML of the main form/content area
        try:
            main_content_html = page.eval_on_selector(
                'main, [role="main"], .content, #content, form, #app, #root',
                "e => e.outerHTML.substring(0, 10000)"
            )
            results["main_content_html_preview"] = main_content_html
        except Exception:
            results["main_content_html_preview"] = "Could not locate main content container"

        # Step 4: Get page title and URL confirmation
        results["page_title"] = page.title()
        results["final_url"] = page.url

        # Step 5: Interactive exploration
        print("\n[5/6] Interactive exploration phase...")
        print("=" * 60)
        print("The browser is now open on the MPOWR create page.")
        print()
        print("INSTRUCTIONS:")
        print("  1. Look at the form and identify all fields")
        print("  2. Try selecting a Tour activity — note which fields appear/change")
        print("  3. Try selecting a Rental activity — note what changes")
        print("  4. Look at the guide add-on section")
        print("  5. Look at the AdventureAssure insurance section")
        print("  6. Check the vehicle count dropdown")
        print("  7. Check the date/time picker")
        print()
        print("When you're done exploring, come back here.")
        print("=" * 60)

        input("\nPress Enter when you've finished exploring the form...")

        # Capture form state after user interaction
        print("\n[6/6] Capturing form elements (after exploration)...")
        ss_path_2 = os.path.join(SCREENSHOT_DIR, "discovery_02_after_exploration.png")
        page.screenshot(path=ss_path_2, full_page=True)
        results["states"]["after_exploration"] = capture_form_elements(page)

        # Save results
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n✅ Discovery complete! Results saved to: {OUTPUT_FILE}")
        print(f"📸 Screenshots saved to: {SCREENSHOT_DIR}/")
        print()
        print("Next steps:")
        print("  1. Review mpowr_form_selectors.json")
        print("  2. Update TBD values in data_mapper.py with exact MPOWR labels")
        print("  3. Update selectors in mpowr_creator_bot.py")

        browser.close()


if __name__ == "__main__":
    run_discovery()
