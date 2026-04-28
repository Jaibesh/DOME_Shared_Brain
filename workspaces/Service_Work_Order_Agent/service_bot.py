import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, expect

# Add workspaces directory to sys.path to import shared modules
WORKSPACE_DIR = Path(__file__).parent.parent
sys.path.append(str(WORKSPACE_DIR))

from shared.mpowr_login import login_to_mpowr
from shared.bot_logger import get_bot_logger

log = get_bot_logger("service_bot", str(Path(__file__).parent / "logs"))

class ServiceBot:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        log.info("Starting Playwright browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            # Mask as standard desktop browser
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()

    def stop(self):
        log.info("Stopping Playwright browser...")
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def run_daily_workflow(self, email: str, password: str):
        """
        Executes the daily work order creation workflow.
        """
        log.info("Starting daily Service Work Order workflow...")
        try:
            # 1. Login
            log.info(f"Logging into MPOWR as {email}...")
            login_to_mpowr(self.page, email, password)

            # 2. Navigate to Vehicles
            self._navigate_to_vehicles()

            # 3. Process Fleet
            self._process_fleet()

            log.info("Daily workflow completed successfully.")
        except Exception as e:
            log.error(f"Workflow failed: {e}")
            # Take screenshot on failure
            try:
                screenshot_path = Path(__file__).parent / "logs" / f"error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path))
                log.info(f"Error screenshot saved to {screenshot_path}")
            except:
                pass
            raise

    def _navigate_to_vehicles(self):
        """Navigates to the vehicles list and sets results per page to 100."""
        log.info("Navigating to Vehicles...")
        
        # Click hamburger menu if needed
        menu_button = self.page.locator('button:has(.fa-bars), .sidebar-toggle, .js-sidebar-toggle, button[aria-label="Toggle Navigation"]').first
        if menu_button.is_visible():
            menu_button.click()
            time.sleep(1)

        # Click Vehicles link in sidebar
        vehicles_link = self.page.locator('a', has_text=re.compile('^Vehicles$', re.IGNORECASE)).first
        vehicles_link.wait_for(state="visible", timeout=10000)
        vehicles_link.click()

        # Wait for vehicle table to load
        self.page.wait_for_url("**/vehicles**", timeout=15000)
        
        # Wait for table rows to actually render (data fetched) BEFORE clicking pagination
        log.info("Waiting for vehicle table data to load...")
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass # Continue even if networkidle times out
        self.page.wait_for_selector('a, button', timeout=10000) # Ensure DOM is interactive
        
        # Change results per page to 100
        log.info("Setting results per page to 100...")
        # Often a dropdown or a button group at the bottom
        results_dropdown = self.page.locator('select').filter(has_text=re.compile('10|25|50|100')).last
        if results_dropdown.is_visible():
            results_dropdown.select_option("100")
            time.sleep(3) # Wait for reload
        else:
            # Might be a custom styled dropdown
            per_page_btn = self.page.locator('button', has_text=re.compile('Results per page|10|25')).last
            if per_page_btn.is_visible():
                per_page_btn.click()
                time.sleep(1) # Wait for dropdown menu animation
                try:
                    self.page.get_by_text("100", exact=True).last.click(timeout=5000)
                except:
                    # Fallback if exact=True fails
                    self.page.locator('text="100"').last.click(timeout=5000)
                time.sleep(3) # Wait for table reload

    def _process_fleet(self):
        """Iterates through vehicles and processes those with past due/due soon tags."""
        
        # We need to process row by row, but the DOM might refresh when going back and forth.
        # It's safer to collect the vehicle URLs or IDs first.
        log.info("Scanning for vehicles with service tags...")
        
        # Collect links to all vehicles that have a badge indicating service is due
        # Badges usually contain text like "Past Due Services" or "Service Due Soon"
        
        # Try to find the rows using a very broad selector
        rows = self.page.locator('tr, div[role="row"], li, .card, div[class*="row"]').all()
        vehicle_urls = []
        
        log.info(f"Scanning {len(rows)} potential DOM rows for service badges...")
        
        for row in rows:
            try:
                text_content = row.inner_text().lower()
                if "past due" in text_content or "due soon" in text_content:
                    # Look for any link in this row that points to a vehicle
                    link = row.locator('a[href*="/vehicles/"]').first
                    if not link.is_visible():
                        # Fallback to the first link if no specific vehicle link is found
                        link = row.locator('a').first
                        
                    if link.is_visible():
                        url = link.get_attribute('href')
                        if url and '/vehicles/' in url:
                            if not url.startswith('http'):
                                base_url = self.page.url.split('/vehicles')[0]
                                url = base_url + url
                            vehicle_urls.append(url)
            except Exception:
                pass
        
        log.info(f"Found {len(vehicle_urls)} vehicles requiring service attention.")
        
        # Deduplicate URLs
        vehicle_urls = list(dict.fromkeys(vehicle_urls))

        for idx, url in enumerate(vehicle_urls):
            log.info(f"Processing vehicle {idx+1}/{len(vehicle_urls)}: {url}")
            self._process_single_vehicle(url)

    def _process_single_vehicle(self, vehicle_url: str):
        try:
            self.page.goto(vehicle_url, timeout=20000)
            
            # Click Service Reminders tab
            service_tab = self.page.locator('a, button, div[role="tab"]').filter(has_text=re.compile('Service Reminders', re.IGNORECASE)).first
            service_tab.wait_for(state="visible", timeout=10000)
            service_tab.click()
            
            time.sleep(2) # Wait for tab content to load
            
            selected_any = False
            
            # 1. Evaluate all checkboxes on the page
            log.info("  Evaluating service tasks...")
            
            # Find all checkboxes
            checkboxes = self.page.locator('input[type="checkbox"]').all()
            for cb in checkboxes:
                try:
                    if cb.is_checked():
                        continue
                        
                    # Find the nearest ancestor container that holds the text 'miles' or 'ago'
                    parent = cb.locator('xpath=ancestor::*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "miles") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "ago")][1]').first
                    
                    if parent.is_visible():
                        # If this container holds multiple checkboxes, it's too high up (e.g., the whole table or the 'Select All' row)
                        if parent.locator('input[type="checkbox"]').count() > 1:
                            continue
                            
                        row_text = parent.inner_text().lower()
                        
                        if "ago" in row_text or "past due" in row_text:
                            try:
                                cb.check(timeout=2000)
                            except:
                                cb.locator('xpath=..').click()
                            selected_any = True
                            log.info(f"  Selected Past Due task: {row_text[:50].strip()}...")
                        elif "miles" in row_text:
                            # Extract miles, accounting for potential commas (e.g., "1,200 miles")
                            match = re.search(r'([\d,]+)\s*miles', row_text)
                            if match:
                                miles_str = match.group(1).replace(',', '')
                                try:
                                    miles = int(miles_str)
                                    if miles < 300:
                                        try:
                                            cb.check(timeout=2000)
                                        except:
                                            cb.locator('xpath=..').click()
                                        selected_any = True
                                        log.info(f"  Selected Upcoming task (<300 miles): {miles} miles - {row_text[:50].strip()}...")
                                    else:
                                        log.info(f"  Skipped Upcoming task (>=300 miles): {miles} miles")
                                except ValueError:
                                    pass
                except Exception as e:
                    continue
            
            if not selected_any:
                log.info("  No tasks selected for work order. Skipping.")
                return
                
            # Create Work Order
            log.info("  Creating Work Order...")
            time.sleep(2) # Give React time to render the Actions button
            actions_btn = self.page.locator('button:visible', has_text=re.compile('Actions', re.IGNORECASE)).last
            actions_btn.click()
            
            time.sleep(1) # Let the dropdown menu animate open
            create_btn = self.page.locator('text="Create work orders"').first
            create_btn.click()
            
            # Confirm modal
            confirm_btn = self.page.locator('button:visible', has_text=re.compile('^Create$', re.IGNORECASE)).first
            confirm_btn.wait_for(state="visible", timeout=5000)
            confirm_btn.click()
            
            # Wait for Work Order Details page to load
            log.info("  Waiting for Work Order Details...")
            self.page.wait_for_url("**/work-orders/**", timeout=15000)
            time.sleep(3) # Give it time to render tasks
            
            # Look for Engine oil & filter replace
            page_text = self.page.inner_text('body').lower()
            if "engine oil & filter" in page_text and "replace" in page_text:
                log.info("  Found 'Engine oil & filter replace'. Injecting Front Differential service...")
                self._inject_differential_service()
            else:
                log.info("  No engine oil replacement found. Work order complete.")
                
        except Exception as e:
            log.error(f"  Failed processing vehicle {vehicle_url}: {e}")

    def _inject_differential_service(self):
        """Updates the work order to add the Front Differential Case Fluid service."""
        
        # Click Actions -> Update
        actions_btn = self.page.locator('button:visible', has_text=re.compile('Actions', re.IGNORECASE)).first
        actions_btn.click()
        
        update_btn = self.page.locator('button, a, li', has_text=re.compile('^Update$', re.IGNORECASE)).first
        update_btn.click()
        
        # Wait for sidebar
        sidebar = self.page.locator('text="Update Work Order"').locator('xpath=ancestor::div[contains(@class, "sidebar") or contains(@class, "modal") or @role="dialog"]').first
        sidebar.wait_for(state="visible", timeout=10000)
        
        # Click Add Service Task
        add_btn = sidebar.locator('button', has_text=re.compile('Add Service Task', re.IGNORECASE)).first
        add_btn.click()
        
        time.sleep(1) # Wait for new row to appear
        
        # The new row is typically the last set of dropdowns.
        # Find all Service Area dropdowns in the sidebar
        service_area_dropdowns = sidebar.locator('label:has-text("Service Area") ~ div').locator('input, select, div[role="combobox"]').all()
        if not service_area_dropdowns:
            # Fallback: find by placeholder or just select elements
            service_area_dropdowns = sidebar.locator('input[placeholder*="Service Area"], div[class*="ServiceArea"]').all()
            
        # MPOWR usually uses a searchable dropdown component (like react-select).
        # Clicking it opens a menu.
        last_area_input = service_area_dropdowns[-1]
        last_area_input.click()
        
        # Type the exact string or click it
        exact_area_string = "Front Differential Gear Case Fluid"
        self.page.keyboard.type(exact_area_string, delay=50)
        time.sleep(1)
        self.page.keyboard.press("Enter")
        
        # Now find Service Task dropdown
        service_task_dropdowns = sidebar.locator('label:has-text("Service Task") ~ div').locator('input, select, div[role="combobox"]').all()
        last_task_input = service_task_dropdowns[-1]
        last_task_input.click()
        
        self.page.keyboard.type("Replace", delay=50)
        time.sleep(1)
        self.page.keyboard.press("Enter")
        
        # Fill Expected Work Hours
        hours_input = sidebar.locator('label:has-text("Expected Work Hours") ~ input, input[name="expectedWorkHours"]').first
        hours_input.fill("1")
        
        # Click Update at the bottom
        bottom_update_btn = sidebar.locator('button', has_text=re.compile('^Update$', re.IGNORECASE)).last
        bottom_update_btn.click()
        
        # Wait for sidebar to close
        sidebar.wait_for(state="hidden", timeout=10000)
        log.info("  Successfully injected differential service.")
