import sys
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

# Add workspaces directory to sys.path to import shared modules
WORKSPACE_DIR = Path(__file__).parent.parent
sys.path.append(str(WORKSPACE_DIR))

from shared.mpowr_login import login_to_mpowr
from shared.bot_logger import get_bot_logger
from shared.shared_utils import cleanup_old_files, reap_playwright_zombies

log = get_bot_logger("service_bot", str(Path(__file__).parent / "logs"))

# Screenshot/log file cleanup settings
LOGS_DIR = Path(__file__).parent / "logs"
SCREENSHOT_MAX_AGE_DAYS = 3


class ServiceBot:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        log.info("Starting Playwright browser...")
        # Kill any zombie Playwright processes from prior crashes
        reap_playwright_zombies()
        
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
        
        # Cleanup old debug screenshots on startup
        removed = cleanup_old_files(str(LOGS_DIR), "*.png", SCREENSHOT_MAX_AGE_DAYS)
        if removed:
            log.info(f"  Cleaned up {removed} old screenshot(s) from logs/")
        
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
                screenshot_path = LOGS_DIR / f"error_{int(time.time())}.png"
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

    def _is_task_eligible(self, row_text: str) -> tuple[bool, str]:
        """Determine if a service task row should be selected for a new work order.
        
        Handles all status categories from MPOWR:
          - Past Due: contains "ago" (e.g., "20 hours ago", "3 days ago")
          - Due Soon: contains "hours" or small mile values (84 miles, 20 hours)
          - Upcoming: contains "miles" with a distance value
        
        Args:
            row_text: Lowercased inner text of the task row container
            
        Returns:
            Tuple of (eligible: bool, reason: str)
        """
        # ── HARD SKIP: rows that already have an open work order ──
        if "open work order" in row_text:
            return False, "has open work order"
        
        # ── Past Due tasks: contain "ago" (e.g., "20 hours ago", "3 days ago") ──
        if "ago" in row_text:
            return True, "past due (contains 'ago')"
        
        # ── Due Soon / Upcoming: check miles and hours ──
        # Due Soon items in MPOWR show "84 miles" / "20 hours" — these are close to due
        # and should ALWAYS be selected regardless of the 300-mile threshold.
        
        # Check hours-based due items (e.g., "20 hours") — always select
        hours_match = re.search(r'(\d+)\s*hours?', row_text)
        if hours_match:
            hours_val = int(hours_match.group(1))
            # Hours-based reminders mean the vehicle is actively near a service interval
            if hours_val < 500:  # Sanity cap — anything under 500 hours is actionable
                return True, f"due soon ({hours_val} hours)"
        
        # Check miles-based items
        miles_match = re.search(r'([\d,]+)\s*miles', row_text)
        if miles_match:
            miles_str = miles_match.group(1).replace(',', '')
            try:
                miles = int(miles_str)
                if miles < 300:
                    return True, f"upcoming (<300 miles: {miles}mi)"
                else:
                    return False, f"too far (>= 300 miles: {miles}mi)"
            except ValueError:
                return False, "miles parse error"
        
        # No recognizable threshold found — skip to be safe
        return False, "no recognized due indicator"

    def _process_single_vehicle(self, vehicle_url: str):
        try:
            self.page.goto(vehicle_url, wait_until='load', timeout=20000)
            time.sleep(3) # Give React a moment to render tabs
            
            # ── Step 1: Navigate directly to Service Reminders tab ──
            # We do NOT skip vehicles with open work orders at the vehicle level.
            # Instead, we skip individual tasks that already have "Open Work Order" badges.
            log.info("  Navigating to Service Reminders tab...")
            service_tab = self.page.get_by_text(re.compile(r'Service Reminders', re.IGNORECASE)).first
            service_tab.click(timeout=5000)
            time.sleep(3) # Wait for tab content to fully load
            
            # ── Step 2: Evaluate checkboxes and select eligible tasks ──
            selected_any = False
            skipped_open_wo = 0
            skipped_too_far = 0
            skipped_other = 0
            selected_count = 0
            log.info("  Evaluating service tasks...")
            
            checkboxes = self.page.locator('input[type="checkbox"]').all()
            log.info(f"  Found {len(checkboxes)} checkboxes on page")
            
            for cb in checkboxes:
                try:
                    if cb.is_checked():
                        continue
                        
                    # ── XPath ancestor scoping with fallback ──
                    # Strategy: Try to find the nearest ancestor containing "miles", "ago", or "hours".
                    # The [1] picks the FIRST matching ancestor (closest to the checkbox).
                    parent = cb.locator(
                        'xpath=ancestor::*['
                        'contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "miles") or '
                        'contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "ago") or '
                        'contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "hours")'
                        '][1]'
                    ).first
                    
                    if not parent.is_visible():
                        continue
                    
                    # Skip if this container holds multiple checkboxes (it's the whole section, not a single row)
                    cb_count = parent.locator('input[type="checkbox"]').count()
                    if cb_count > 1:
                        skipped_other += 1
                        # Log with context so we can debug XPath scoping issues
                        try:
                            snippet = parent.inner_text()[:40].strip().replace('\n', ' ')
                            log.debug(f"  XPath landed on section-level container ({cb_count} checkboxes): {snippet}...")
                        except:
                            pass
                        continue
                        
                    row_text = parent.inner_text().lower()
                    
                    # Use centralized eligibility check
                    eligible, reason = self._is_task_eligible(row_text)
                    
                    if not eligible:
                        if "open work order" in reason:
                            skipped_open_wo += 1
                        elif "too far" in reason or ">= 300" in reason:
                            skipped_too_far += 1
                        else:
                            skipped_other += 1
                        log.info(f"  Skipped ({reason}): {row_text[:60].strip()}")
                        continue
                    
                    # Eligible — click the checkbox
                    try:
                        cb.click(timeout=2000)
                    except:
                        cb.locator('xpath=..').click(timeout=2000)
                    selected_any = True
                    selected_count += 1
                    log.info(f"  Selected task ({reason}): {row_text[:60].strip()}")
                        
                except Exception as ex:
                    log.debug(f"  Checkbox evaluation error (non-fatal): {ex}")
                    continue
            
            log.info(f"  Summary: {selected_count} selected, {skipped_open_wo} skipped (open WO), {skipped_too_far} skipped (>=300mi), {skipped_other} skipped (other)")
            
            if not selected_any:
                log.info("  No tasks selected for work order. Skipping.")
                return
                
            # ── Step 3: Click "Create work orders" button ──
            log.info("  Creating Work Order...")
            time.sleep(2) # Give React time to render the button
            
            # Take a screenshot before clicking so we can debug if needed
            try:
                pre_click_path = LOGS_DIR / f"pre_create_{int(time.time())}.png"
                self.page.screenshot(path=str(pre_click_path))
            except:
                pass
            
            # Click the "Create work orders" button
            create_btn = self.page.get_by_text(re.compile(r'Create work order', re.IGNORECASE)).last
            create_btn.click(timeout=10000)
            
            # ── Step 4: Wait for work order to be created ──
            # MPOWR does NOT show a confirmation modal - it creates the work order directly.
            log.info("  Work order creation initiated. Waiting for page to settle...")
            time.sleep(5) # Give MPOWR time to process
            
            # Take a post-creation screenshot for verification
            try:
                post_click_path = LOGS_DIR / f"post_create_{int(time.time())}.png"
                self.page.screenshot(path=str(post_click_path))
            except:
                pass
            
            # ── Step 5: Navigate directly to the vehicle's Work Orders page ──
            log.info("  Navigating to vehicle's Work Orders page to verify creation...")
            # Build the work orders URL from the vehicle URL
            # e.g., .../vehicles/A-EJA-NGR/details -> .../vehicles/A-EJA-NGR/work-orders
            wo_url = vehicle_url.split('/details')[0] + '/work-orders'
            self.page.goto(wo_url, wait_until='load', timeout=20000)
            time.sleep(3)
            
            # Take a screenshot so we can see what the Work Orders page looks like
            try:
                wo_page_path = LOGS_DIR / f"wo_page_{int(time.time())}.png"
                self.page.screenshot(path=str(wo_page_path))
                log.info(f"  Work Orders page screenshot: {wo_page_path}")
            except:
                pass
            
            # Click the top-most (newest) work order link in the list
            try:
                first_wo_link = self.page.locator('a[href*="/work-orders/"]').first
                if first_wo_link.is_visible(timeout=5000):
                    log.info("  ✅ Work order created successfully! Opening details...")
                    first_wo_link.click(timeout=5000)
                    time.sleep(3) # Give it time to render the work order details
                    
                    # Check if we need to inject the Front Differential service
                    page_text = self.page.inner_text('body').lower()
                    if "engine oil" in page_text and "filter" in page_text and "replace" in page_text:
                        log.info("  Found 'Engine oil & filter replace'. Injecting Front Differential service...")
                        self._inject_differential_service()
                    else:
                        log.info("  No engine oil replacement found. Work order complete.")
                else:
                    log.warning("  Could not find work order link after reload. Work order may not have been created.")
            except Exception as e:
                log.warning(f"  Could not open work order details for differential injection: {e}")
                
        except Exception as e:
            log.error(f"  Failed processing vehicle {vehicle_url}: {e}")
            try:
                screenshot_path = LOGS_DIR / f"error_vehicle_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path))
                log.info(f"  Error screenshot saved to {screenshot_path}")
            except:
                pass

    def _inject_differential_service(self):
        """Updates the work order to add the Front Differential Case Fluid service.
        
        Wrapped in comprehensive error handling with screenshot capture,
        since the sidebar locator strategy depends on MPOWR's current component structure.
        """
        try:
            # Click Actions -> Update
            actions_btn = self.page.locator('button:visible', has_text=re.compile('Actions', re.IGNORECASE)).first
            actions_btn.click()
            time.sleep(0.5)
            
            update_btn = self.page.locator('button, a, li', has_text=re.compile('^Update$', re.IGNORECASE)).first
            update_btn.click()
            time.sleep(1)
            
            # Wait for sidebar — try multiple locator strategies for resilience
            sidebar = None
            sidebar_strategies = [
                # Strategy 1: Find "Update Work Order" text and walk up to sidebar container
                lambda: self.page.locator('text="Update Work Order"').locator(
                    'xpath=ancestor::div[contains(@class, "sidebar") or contains(@class, "modal") or @role="dialog"]'
                ).first,
                # Strategy 2: Generic dialog/drawer selectors
                lambda: self.page.locator('div[role="dialog"], [class*="drawer"], [class*="sidebar"], [class*="SlideOver"]').last,
                # Strategy 3: Any visible panel containing "Update Work Order"
                lambda: self.page.locator('div').filter(
                    has=self.page.get_by_text("Update Work Order")
                ).filter(
                    has=self.page.locator('button', has_text=re.compile('^Update$', re.IGNORECASE))
                ).last,
            ]
            
            for i, strategy in enumerate(sidebar_strategies):
                try:
                    candidate = strategy()
                    candidate.wait_for(state="visible", timeout=5000)
                    sidebar = candidate
                    log.info(f"  Sidebar found via strategy {i + 1}")
                    break
                except:
                    continue
            
            if not sidebar:
                log.warning("  ⚠️ Could not locate Update Work Order sidebar. Taking diagnostic screenshot.")
                try:
                    diag_path = LOGS_DIR / f"sidebar_fail_{int(time.time())}.png"
                    self.page.screenshot(path=str(diag_path))
                    log.info(f"  Diagnostic screenshot: {diag_path}")
                except:
                    pass
                return
            
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
            log.info("  ✅ Successfully injected differential service.")
            
        except Exception as e:
            log.error(f"  ❌ Differential service injection failed: {e}")
            # Capture diagnostic screenshot so we can see what state the UI is in
            try:
                diag_path = LOGS_DIR / f"inject_fail_{int(time.time())}.png"
                self.page.screenshot(path=str(diag_path))
                log.info(f"  Diagnostic screenshot saved: {diag_path}")
            except:
                pass
