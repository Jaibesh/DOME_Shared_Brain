"""
mpowr_creator_bot.py — Core Playwright UI Automation Engine

Two-phase bot:
  Phase A: Creates a reservation by filling out the MPOWR /orders/create form
  Phase B: Verifies the price and overrides if it doesn't match TripWorks

Every error path captures a screenshot and sends a Slack DM.
Ships with DRY_RUN mode — fills the form but does NOT click Submit.
"""

import os
import re
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from mpowr_login import login_to_mpowr, MpowrLoginError
from data_mapper import (
    select_best_time_slot,
    parse_subtotal,
)
from slack_notifier import SlackNotifier
from bot_logger import get_bot_logger

# Module-level logger instance
log = get_bot_logger()

# ---------------------------------------------------------------------------
# Configuration — Timeouts in milliseconds
# ---------------------------------------------------------------------------
TIMEOUTS = {
    "login_page_load": 20000,
    "login_complete": 15000,
    "create_page_load": 15000,
    "form_field_visible": 8000,
    "dropdown_option": 5000,
    "date_picker_open": 5000,
    "time_picker": 5000,
    "vehicle_dropdown": 5000,
    "guide_addons": 5000,
    "insurance": 5000,
    "submit_navigation": 30000,
    "price_page_load": 10000,
    "price_override": 10000,
    "between_reservations": 3000,
}

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Maximum consecutive failures before aborting batch (prevents runaway errors)
MAX_CONSECUTIVE_FAILURES = 3


def _dual_print(*args, **kwargs):
    """Print to both console and the structured log file.

    This wraps the built-in print() so that every existing print() call
    in create_reservation (and helpers) is automatically captured in the
    JSON log file without needing to replace 100+ individual calls.

    EDGE-7 FIX: Routes to correct log severity based on emoji/keyword prefix.
    LOW-5 FIX: Uses emoji-first detection to prevent false positives
    (e.g. "No errors found!" was being logged as error-level).
    """
    import builtins
    msg = " ".join(str(a) for a in args)
    builtins.print(msg, **kwargs)

    # Route to appropriate log level — check emojis first (most reliable),
    # then keywords only at the START of the message (not substring)
    if "❌" in msg or "FAIL" in msg.upper()[:15]:
        log.error(msg)
    elif "⚠️" in msg:
        log.warning(msg)
    elif "✅" in msg or "📸" in msg:
        log.info(msg)
    elif msg.lstrip().lower().startswith("error"):
        log.error(msg)
    else:
        log.debug(msg)


# Override print for this module so all output is logged
print = _dual_print

# ---------------------------------------------------------------------------
# Selectors — PERF-4: Stored as LISTS to avoid comma-split ambiguity
# ---------------------------------------------------------------------------
SELECTORS = {
    # Customer info fields
    "email_input": ["input[name*='email' i]", "input[placeholder*='email' i]"],
    "first_name_input": ["input[name*='firstName' i]", "input[placeholder*='first' i]"],
    "last_name_input": ["input[name*='lastName' i]", "input[placeholder*='last' i]"],
    "phone_input": ["input[name*='phone' i]", "input[placeholder*='phone' i]"],

    # Activity/listing selector (custom dropdown)
    "activity_dropdown": ["button:has-text('Choose Listing')"],

    # Vehicle selector (Add Vehicle button)
    "vehicle_dropdown": ["button:has-text('Add Vehicle')"],

    # Date / Time
    "date_input": ["input[placeholder*='MM / DD / YYYY' i]", "input[type='date']"],
    "time_dropdown": ["button:has-text('Select Time')", "select[id*='time']"],

    # Insurance
    "insurance_section": ["text='AdventureAssure'", "text='Protection'"],
    "insurance_free": ["button:has-text('Free')", "input[value*='free' i]"],

    # Submit button
    "submit_button": ["button:has-text('Reserve Now')", "button[type='submit']"],

    # Post-creation price override
    "actions_button": ["button:has-text('Options')", "button:has-text('Actions')"],
    "override_price_option": ["text='Override Pricing'", "text='Override Price'", "text='Edit Price'"],
    "price_input": ["input[aria-label*='Price' i]", "input[type='number']"],
    "price_save_button": ["button:has-text('Apply')", "button:has-text('Save')"],

    "total_price_display": ["text='orderTotalEstimate' ~ div", "[class*='total']"],
}


class CreationResult:
    """Result of a single reservation creation attempt."""

    def __init__(self, status: str, mpowr_conf_id: str | None = None,
                 error_message: str | None = None, screenshot_path: str | None = None,
                 price_overridden: bool = False):
        self.status = status  # 'success', 'error', 'duplicate', 'dry_run'
        self.mpowr_conf_id = mpowr_conf_id
        self.error_message = error_message
        self.screenshot_path = screenshot_path
        self.price_overridden = price_overridden

    def __repr__(self):
        return f"CreationResult(status={self.status}, id={self.mpowr_conf_id}, error={self.error_message})"


class MpowrCreatorBot:
    """
    Playwright UI automation bot that creates MPOWR reservations
    by filling out the web form at /orders/create.

    Usage:
        bot = MpowrCreatorBot(email, password, dry_run=True)
        results = bot.create_batch(customer_payloads)
    """

    def __init__(self, email: str, password: str, headless: bool = True,
                 dry_run: bool = True):
        """
        Args:
            email: MPOWR login email
            password: MPOWR login password
            headless: Run Chromium headlessly (True for production)
            dry_run: If True, fill form but DO NOT click Submit
        """
        self.email = email
        self.password = password
        self.headless = headless
        self.dry_run = dry_run
        self.slack = SlackNotifier()
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def _start_browser(self):
        """Launch Playwright and login to MPOWR."""
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        self._page = self._context.new_page()

        # SEC-3: Log dialog messages before accepting — prevents silent auto-accept of dangerous dialogs
        def _handle_dialog(dialog):
            msg = dialog.message
            log.warning(f"[Browser Dialog] Type={dialog.type}, Message='{msg}'. Auto-accepting.")
            dialog.accept()
        self._page.on("dialog", _handle_dialog)

        login_to_mpowr(self._page, self.email, self.password)

    def _close_browser(self):
        """Safely close browser resources."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception as e:
            log.warning(f"[Creator Bot] Error closing browser: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None

    def _screenshot(self, label: str) -> str:
        """Take a screenshot and return the file path."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_{ts}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        try:
            # PERF-3: Use viewport-only screenshots (not full_page) to reduce file size
            # Full-page captures ~500 KB each; viewport captures ~150 KB
            self._page.screenshot(path=path, full_page=False)
        except Exception as e:
            log.warning(f"[Creator Bot] Screenshot failed: {e}")
        return path

    # -----------------------------------------------------------------------
    # Session Health & Re-Authentication
    # -----------------------------------------------------------------------

    def _is_session_alive(self) -> bool:
        """Check if the MPOWR session is still valid.

        Navigates to /orders/create and checks if MPOWR redirects to the
        login page. If the URL contains 'login' or 'auth', the session
        has expired.

        Returns:
            True if session is valid, False if expired
        """
        try:
            self._page.goto("https://mpwr-hq.poladv.com/orders/create",
                           timeout=TIMEOUTS["create_page_load"],
                           wait_until="domcontentloaded")
            time.sleep(2)
            current_url = self._page.url.lower()

            if "login" in current_url or "auth" in current_url or "signin" in current_url:
                log.warning("[Session] Session expired — URL redirected to login page")
                return False

            # Also check if the page has a login form (SSO gateway)
            login_form = self._page.locator("#username")
            if login_form.count() > 0:
                log.warning("[Session] Session expired — login form detected on page")
                return False

            return True
        except Exception as e:
            log.error(f"[Session] Session health check failed: {e}")
            return False

    def _reauth(self) -> bool:
        """Re-authenticate to MPOWR without restarting the browser.

        Attempts to login again using the existing page. If the page is
        on the login screen, fills credentials and submits. If that fails,
        tears down the entire browser and starts fresh.

        Returns:
            True if re-auth succeeded, False if it failed
        """
        log.info("[Session] Attempting re-authentication...")

        try:
            # First attempt: login on the current page (session expired but browser ok)
            login_to_mpowr(self._page, self.email, self.password)
            log.info("[Session] Re-authentication successful (same browser)")
            return True
        except MpowrLoginError:
            log.warning("[Session] Re-auth on same page failed. Restarting browser...")

        try:
            # Second attempt: full browser restart
            self._close_browser()
            time.sleep(2)
            self._start_browser()
            log.info("[Session] Re-authentication successful (browser restart)")
            return True
        except Exception as e:
            log.error(f"[Session] Full re-auth failed: {e}")
            return False


    # -----------------------------------------------------------------------
    # Helper: Try multiple selectors
    # -----------------------------------------------------------------------

    def _find_element(self, selector_key: str, timeout: int = None):
        """
        Try to find an element using the selector list defined in SELECTORS dict.
        PERF-4: Selectors are stored as lists, not comma-separated strings.
        """
        timeout = timeout or TIMEOUTS["form_field_visible"]
        selectors = SELECTORS.get(selector_key)

        # If selector_key is not in SELECTORS, treat it as a raw CSS selector
        if selectors is None:
            selectors = [selector_key]
        elif isinstance(selectors, str):
            selectors = [selectors]  # Backward compat: single string

        for sel in selectors:
            try:
                self._page.wait_for_selector(sel, timeout=timeout)
                return self._page.locator(sel).first
            except Exception:
                continue

        return None

    def _safe_fill(self, selector_key: str, value: str, label: str = "") -> bool:
        """Try to fill an input field. Returns True if successful."""
        element = self._find_element(selector_key)
        if element:
            try:
                element.fill(value)
                print(f"  ✅ Filled {label or selector_key}: {value}")
                return True
            except Exception as e:
                print(f"  ❌ Failed to fill {label or selector_key}: {e}")
                return False
        else:
            print(f"  ❌ Element not found: {label or selector_key}")
            return False

    def _safe_select(self, selector_key: str, value: str, label: str = "") -> bool:
        """Try to select a dropdown option. Handles both native <select> and custom MPOWR dropdowns."""
        element = self._find_element(selector_key)
        if element:
            # Check if it's a native select
            is_select = element.evaluate("e => e.tagName.toLowerCase() === 'select'")
            if is_select:
                try:
                    element.select_option(label=value)
                    print(f"  ✅ Selected {label or selector_key}: {value}")
                    return True
                except Exception:
                    try:
                        element.select_option(value=value)
                        print(f"  ✅ Selected {label or selector_key} (by value): {value}")
                        return True
                    except Exception as e:
                        print(f"  ❌ Failed to select {label or selector_key}: {e}")
                        return False
            
            # Custom MPOWR Dropdown: click the button, then click the text option
            try:
                element.click()
                time.sleep(1)
                
                # MPOWR uses visual cards instead of standard listbox options! 
                # get_by_text(exact=False) parses the DOM for our exact prefix regardless of HTML tags, ignoring quoting errors.
                option = self._page.get_by_text(value, exact=False).filter(visible=True).first
                
                if option.is_visible():
                    option.click()
                    print(f"  ✅ Selected custom {label or selector_key}: {value}")
                    return True
                else:
                    # Fallback click outside to close if not found
                    self._page.mouse.click(0, 0)
                    print(f"  ❌ Option text not visible: {value}")
                    return False
            except Exception as e:
                print(f"  ❌ Failed to interact with custom dropdown {label or selector_key}: {e}")
                return False
        else:
            print(f"  ❌ Dropdown not found: {label or selector_key}")
            return False

    # -----------------------------------------------------------------------
    # Phase A: Create Reservation
    # -----------------------------------------------------------------------

    def create_reservation(self, customer: dict) -> CreationResult:
        """
        Creates a single MPOWR reservation by filling the /orders/create form.

        Args:
            customer: Dict from data_mapper.build_customer_payload_from_row()
                Required keys: webhook_email, first_name, last_name, phone,
                mpowr_activity, mpowr_vehicle, vehicle_qty, activity_date,
                activity_time, guide_addons, insurance_label, target_price,
                tw_confirmation, activity, booking_type

        Returns:
            CreationResult with status, confirmation ID, error details
        """
        name = f"{customer['first_name']} {customer['last_name']}"
        tw_conf = customer.get("tw_confirmation", "")

        print(f"\n{'='*60}")
        print(f"Creating reservation for: {name} (TW: {tw_conf})")
        print(f"Activity: {customer['activity']} → MPOWR: {customer['mpowr_activity']}")
        print(f"Vehicle: {customer['mpowr_vehicle']} x{customer['vehicle_qty']}")
        print(f"Date: {customer['activity_date']} Time: {customer['activity_time']}")
        print(f"DRY RUN: {self.dry_run}")
        print(f"{'='*60}")

        try:
            # Step 1: Navigate to create page
            print("\n[Step 1] Navigating to /orders/create...")
            self._page.goto("https://mpwr-hq.poladv.com/orders/create",
                           timeout=TIMEOUTS["create_page_load"], wait_until="domcontentloaded")
            time.sleep(3)

            # Step 2: Select activity/listing (FIRST — other fields depend on this)
            print(f"\n[Step 2] Selecting activity: {customer['mpowr_activity']}...")
            activity_selected = False
            try:
                # Click the "Choose Listing" button/card to open the listing modal
                listing_btn = self._page.locator("button").filter(has_text=re.compile("Choose Listing|Hell|Poison|Moab|Hour|Half-Day|Full-Day|Multi-Day|Slingshot|Revenge|Spider|Discovery")).first
                listing_btn.click()
                time.sleep(2)

                # Wait for the Choose Listing modal with role="radiogroup"
                self._page.wait_for_selector("[role='radiogroup']", timeout=5000)

                # CRITICAL: The modal uses a VIRTUALIZED LIST — only ~8 of 10 listings
                # are rendered in the DOM at any time. Hell's Revenge and Moab Discovery Tour
                # are at the BOTTOM and must be scrolled into view to exist in the DOM.
                # The scrollable container is: div.fixed.inset-0.z-10.overflow-y-auto
                target = customer["mpowr_activity"]
                
                # Also handle curly vs straight apostrophes (Hell's vs Hell's)
                target_variants = [target]
                if "'" in target:
                    target_variants.append(target.replace("'", "\u2019"))  # curly right single quote
                if "\u2019" in target:
                    target_variants.append(target.replace("\u2019", "'"))

                # Try to find the card, scrolling through the virtualized list
                scroll_container = self._page.locator("div.fixed.inset-0.z-10.overflow-y-auto").first
                
                for scroll_attempt in range(6):  # Max 6 scroll attempts
                    for tv in target_variants:
                        # Find ALL matching cards (there may be multiple substring matches)
                        cards = self._page.locator("[role='radio']").filter(has_text=tv)
                        card_count = cards.count()
                        
                        for ci in range(card_count):
                            candidate = cards.nth(ci)
                            try:
                                card_text = candidate.inner_text(timeout=1000).strip().lower()
                            except Exception:
                                card_text = ""
                            
                            # BLOCKLIST CHECK: Skip special events, meetups, etc.
                            is_blocked = any(bl in card_text for bl in self.SPECIAL_EVENT_BLOCKLIST)
                            if is_blocked:
                                print(f"  ⏭️ Skipping blocked listing: {card_text[:60]}")
                                continue
                            
                            # Valid card found!
                            candidate.scroll_into_view_if_needed()
                            time.sleep(0.3)
                            candidate.click()
                            activity_selected = True
                            print(f"  ✅ Selected listing: {tv} (scroll attempt {scroll_attempt})")
                            time.sleep(2)
                            break
                        
                        if activity_selected:
                            break
                    
                    if activity_selected:
                        break
                    
                    # Scroll the modal overlay down to render more virtualized items
                    scroll_container.evaluate("el => el.scrollBy(0, 400)")
                    time.sleep(0.5)
                    print(f"  ⏳ Scrolling modal... (attempt {scroll_attempt + 1})")

                if not activity_selected:
                    # Final fallback: try get_by_text with each variant
                    for tv in target_variants:
                        card_fb = self._page.get_by_text(tv, exact=False).first
                        if card_fb.count() > 0:
                            try:
                                fb_text = card_fb.inner_text(timeout=1000).strip().lower()
                            except Exception:
                                fb_text = ""
                            is_blocked = any(bl in fb_text for bl in self.SPECIAL_EVENT_BLOCKLIST)
                            if is_blocked:
                                print(f"  ⏭️ Skipping blocked fallback: {fb_text[:60]}")
                                continue
                            card_fb.scroll_into_view_if_needed()
                            time.sleep(0.3)
                            card_fb.click()
                            activity_selected = True
                            print(f"  ✅ Selected listing (fuzzy): {tv}")
                            time.sleep(2)
                            break
                    
                    if not activity_selected:
                        print(f"  ❌ Listing card not found after scrolling: {target}")

            except Exception as e:
                print(f"  ❌ Activity selection error: {e}")

            if not activity_selected:
                ss = self._screenshot(f"error_activity_{tw_conf}")
                return CreationResult(
                    status="error",
                    error_message=f"Cannot select activity: {customer['mpowr_activity']}",
                    screenshot_path=ss,
                )

            # Wait for dependent fields to update after activity selection
            # MED-1 FIX: Was duplicated — only need one 2s wait
            time.sleep(2)

            # Step 3: Select date
            print("\n[Step 3] Setting date...")
            self._handle_date_selection(customer)

            # Wait for date to settle and MPOWR to fetch inventory
            time.sleep(2)

            # Step 4: Select time slot
            print("\n[Step 4] Setting time slot...")
            self._handle_time_selection(customer.get("activity_time", ""))

            # Wait for MPOWR to refresh vehicle inventory for this date/time
            print("  \u23f3 Waiting for MPOWR inventory refresh...")
            time.sleep(3)

            # Step 5: Select Vehicle & Quantity
            vehicles = customer.get("vehicles", [{"model": customer["mpowr_vehicle"], "qty": customer.get("vehicle_qty", 1)}])
            print(f"\n[Step 5] Selecting {len(vehicles)} vehicle type(s)...")
            for v in vehicles:
                print(f"  -> Selecting {v['model']} (Quantity: {v['qty']})")
                self._handle_vehicle_selection(v["model"], str(v["qty"]))

            # Step 6: Wait for Add-on/Summary updates
            time.sleep(1)

            # Step 7: Select insurance (AdventureAssure)
            print("\n[Step 7] Selecting insurance...")
            self._handle_insurance_selection(customer.get("insurance_label", ""))

            # Step 8: Select guide add-on(s) (tours only — may have MIXED guide types)
            guide_addons = customer.get("guide_addons", [])
            if guide_addons:
                guide_summary = ", ".join(f"{g['label']} x{g['quantity']}" for g in guide_addons)
                print(f"\n[Step 8] Selecting guide add-on(s): {guide_summary}...")
                self._handle_guide_addons(guide_addons)
            else:
                print("\n[Step 8] No guide add-on (rental or not applicable)")

            # Step 9: Additional Questions (Mandatory Checkboxes)
            print("\n[Step 9] Answering required questions...")
            time.sleep(1)
            self._handle_additional_questions()

            # Step 10: Fill customer info (at BOTTOM of the form)
            print("\n[Step 10] Filling customer info...")
            # Scroll down to ensure customer info section is visible
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            # Use get_by_role("textbox") with exact name to avoid checkbox label collisions
            # (get_by_label("Email") was colliding with the OHV checkbox label)
            self._page.get_by_role("textbox", name="First Name", exact=True).fill(customer["first_name"])
            self._page.get_by_role("textbox", name="Last Name", exact=True).fill(customer["last_name"])
            self._page.get_by_role("textbox", name="Email", exact=True).fill(customer["webhook_email"])
            if customer.get("phone"):
                self._page.get_by_role("textbox", name="Phone", exact=True).fill(customer["phone"])
            print(f"  ✅ Customer info filled: {name} / {customer['webhook_email']}")

            # Step 11: Pre-submit screenshot
            print("\n[Step 11] Pre-submit screenshot...")
            ss_pre = self._screenshot(f"pre_submit_{tw_conf}")
            print(f"  \U0001f4f8 Saved: {ss_pre}")

            if self.dry_run:
                ss_pre = self._screenshot(f"dryrun_ready_{tw_conf}")
                print(f"\n[DRY RUN] Would click Submit now for {name}")
                return CreationResult(
                    status="dry_run",
                    screenshot_path=ss_pre,
                    error_message=f"DRY_RUN: Would create reservation for {name}",
                )

            # Phase B: Price verification Shifted BEFORE Submission
            price_overridden = False
            target_price = customer.get("target_price", 0)
            if target_price > 0:
                price_overridden = self._verify_and_override_price(
                    target_price, name, tw_conf, customer.get("vehicle_qty", 1)
                )

            print("\n[Step 12] Clicking Submit...")
            submit = self._find_element("submit_button")
            if not submit:
                ss = self._screenshot(f"error_no_submit_{tw_conf}")
                return CreationResult(
                    status="error",
                    error_message="Submit button not found",
                    screenshot_path=ss,
                )

            submit.click()

            print("\n[Step 12.5] Monitoring for 'Charge Later' payment modal...")
            for _ in range(30):  # Poll every 0.5s for up to 15 seconds
                try:
                    # Break early if we've successfully navigated past the creation form
                    if "/orders/" in self._page.url and "/create" not in self._page.url:
                        break

                    # Look for the Charge Later button
                    cl_btn = self._page.get_by_role("button", name=re.compile(r"charge later", re.IGNORECASE)).first
                    if cl_btn.count() > 0 and cl_btn.is_visible():
                        cl_btn.click()
                        print("  ✅ Clicked 'Charge Later' on payment popup")
                        time.sleep(1) # wait for MPOWR to process the modal
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            # Step 13: Wait for success navigation
            # BUG-5 FIX: Wait for URL containing /orders/ followed by a digit (the conf ID)
            # The old pattern **/orders/** matched the CREATE page URL itself, causing
            # false-positive success if submit failed silently (e.g., form validation error).
            print("\n[Step 13] Waiting for confirmation...")
            try:
                self._page.wait_for_url(re.compile(r'/orders/(?!create\b)[A-Za-z0-9-]+'), timeout=TIMEOUTS["submit_navigation"])
                time.sleep(2)
            except Exception as e:
                # EDGE-2 FIX: Check if an error toast appeared on failure to diagnose API 500s natively
                error_msg = ""
                try:
                    toast = self._page.locator(".Toastify__toast-body, .error, .text-red-500, [role='alert']").first
                    if toast.is_visible(timeout=1000):
                        error_msg = f" UI Error: '{toast.inner_text().strip()}'"
                except Exception:
                    pass
                
                ss = self._screenshot(f"error_submit_timeout_{tw_conf}")
                return CreationResult(
                    status="error",
                    error_message=f"Submit timeout — no navigation.{error_msg}",
                    screenshot_path=ss,
                )

            # Step 14: Extract confirmation ID from URL
            current_url = self._page.url
            # Negative lookahead explicitly prevents parsing /orders/create as a successful conf ID extraction
            conf_match = re.search(r'/orders/(?!create\b)([A-Za-z0-9-]+)', current_url)

            if conf_match:
                conf_id = conf_match.group(1)
                print(f"  ✅ Reservation created! MPOWR ID: {conf_id}")
            else:
                ss = self._screenshot(f"error_no_conf_id_{tw_conf}")
                return CreationResult(
                    status="error",
                    error_message=f"Created but can't extract ID from URL: {current_url}",
                    screenshot_path=ss,
                )

            ss_final = self._screenshot(f"success_{tw_conf}_{conf_id}")
            return CreationResult(
                status="success",
                mpowr_conf_id=conf_id,
                screenshot_path=ss_final,
                price_overridden=price_overridden,
            )

        except Exception as e:
            ss = self._screenshot(f"error_unexpected_{tw_conf}")
            error_msg = f"Unexpected error: {str(e)}"
            print(f"  ❌ {error_msg}")
            return CreationResult(
                status="error",
                error_message=error_msg,
                screenshot_path=ss,
            )

    # -----------------------------------------------------------------------
    # Phase B: Price Verification & Override
    # -----------------------------------------------------------------------

    def _verify_and_override_price(self, target_price: float, 
                                    customer_name: str, tw_conf: str, vehicle_qty: int = 1) -> bool:
        """
        After creating a reservation, verifies the MPOWR price matches TripWorks.
        If not, uses Actions → Override Price to adjust.

        Returns True if price was overridden, False if it matched or override failed.
        """
        print(f"\n[Price Check] Target: ${target_price:.2f} (Qty: {vehicle_qty})")

        try:
            # Read MPOWR's displayed price
            time.sleep(2)
            # Search explicitly for "Subtotal" since TripWorks target_price excludes MPOWR's native tax generation
            try:
                subtotal_node = self._page.get_by_text("Subtotal", exact=True).first
                if subtotal_node.is_visible(timeout=5000):
                    price_text = subtotal_node.evaluate("el => el.parentElement.innerText")
                else:
                    # Fallback to total_price_display if Subtotal is totally missing from DOM
                    fallback_element = self._find_element("total_price_display", timeout=5000)
                    price_text = fallback_element.inner_text() if fallback_element else ""
            except Exception as e:
                print(f"  ⚠️ Error finding Subtotal element: {e}. Skipping price check.")
                return False

            if not price_text:
                print("  ⚠️ Price element is empty. Skipping price check.")
                return False

            # Parse price accommodating whole numbers like "$878" and standard "$340.23"
            price_num = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', price_text)
            if not price_num:
                price_num = re.search(r'([\d,]+(?:\.\d{2})?)', price_text.replace(",", ""))
                if not price_num:
                    print(f"  ⚠️ Could not parse actual numerical price from: '{price_text}'")
                    return False
                    
            mpowr_price = float(price_num.group(1).replace(",", ""))
            print(f"  MPOWR Subtotal Price: ${mpowr_price:.2f}")

            # Check if prices match (within $0.01 tolerance)
            if abs(mpowr_price - target_price) < 0.02:
                print(f"  ✅ Prices match!")
                return False

            # Price mismatch — override needed
            print(f"  ⚠️ Price mismatch! MPOWR: ${mpowr_price:.2f} vs TripWorks: ${target_price:.2f}")
            print(f"  Difference: ${abs(mpowr_price - target_price):.2f}")

            # Click Actions dropdown (top-right)
            actions_btn = self._find_element("actions_button", timeout=5000)
            if not actions_btn:
                print("  ❌ Actions button not found. Manual override required.")
                self.slack.send_price_override_alert(
                    customer_name, tw_conf, mpowr_price, target_price, False, "<Pending>"
                )
                return False

            actions_btn.click()
            time.sleep(1)

            # Click "Override Price"
            override_btn = self._find_element("override_price_option", timeout=3000)
            if not override_btn:
                print("  ❌ Override Price option not found.")
                self.slack.send_price_override_alert(
                    customer_name, tw_conf, mpowr_price, target_price, False, "<Pending>"
                )
                return False

            override_btn.click()
            time.sleep(1)

            # Find all price input fields in the override modal using comma-separated fallbacks
            price_inputs = self._page.locator(", ".join(SELECTORS["price_input"]))
            input_count = price_inputs.count()
            
            if input_count == 0:
                # Try generic number input fallback
                price_inputs = self._page.locator("input[type='number']")
                input_count = price_inputs.count()
                
            if input_count == 0:
                print("  ❌ Price input field not found in override modal.")
                ss = self._screenshot(f"error_price_override_{tw_conf}")
                self.slack.send_price_override_alert(
                    customer_name, tw_conf, mpowr_price, target_price, False, "<Pending>"
                )
                return False

            # Calculate difference needed PER input/vehicle unit
            difference = target_price - mpowr_price
            
            # Usually, MPOWR provides N inputs for N vehicles. Or perhaps one input per line item.
            # We will split the difference equally among all found vehicle inputs,
            # up to the expected vehicle_qty.
            num_to_adjust = min(input_count, vehicle_qty)

            # EDGE-1: Calculate base_diff mathematically to exactly 2 decimals and assign unresolved trailing remainder to the 1st vehicle explicitly
            base_diff = round(difference / num_to_adjust, 2)
            remainder = round(difference - (base_diff * num_to_adjust), 2)
            
            print(f"  Found {input_count} price inputs. Applying diff of ${base_diff:+.2f} per item (+ ${remainder:+.2f} remainder across {num_to_adjust} items).")

            for i in range(num_to_adjust):
                price_input = price_inputs.nth(i)
                current_val_str = price_input.input_value()
                try:
                    current_val = float(current_val_str.replace('$', '').replace(',', ''))
                except ValueError:
                    current_val = 0.0
                    
                target_diff = base_diff + remainder if i == 0 else base_diff
                new_vehicle_price = current_val + target_diff

                # Apply the specific difference to the vehicle's price
                price_input.fill("")
                price_input.fill(f"{new_vehicle_price:.2f}")
                print(f"  Adjusted vehicle {i+1} price from ${current_val:.2f} to ${new_vehicle_price:.2f} (Diff: ${target_diff:+.2f})")

            # Save the override
            save_btn = self._find_element("price_save_button", timeout=3000)
            if save_btn:
                save_btn.click()
                time.sleep(2)
                print(f"  ✅ Price overridden successfully.")
                try:
                    self.slack.send_price_override_alert(
                        customer_name, tw_conf, mpowr_price, target_price, True, "<Pending>"
                    )
                except Exception as slack_err:
                    print(f"  ⚠️ Slack price alert failed (non-fatal): {slack_err}")
                return True
            else:
                print("  ❌ Save button not found after price override.")
                return False

        except Exception as e:
            print(f"  ❌ Price verification error: {e}")
            return False

    # -----------------------------------------------------------------------
    # Form Interaction Helpers
    # -----------------------------------------------------------------------

    def _handle_date_selection(self, customer: dict):
        """Handle date picker by clicking calendar icon and navigating to target date.

        BUG-3 FIX: Supports multiple date formats from Google Sheets.
        MULTI-DAY FIX: Supports "Multi-Day Adventure Rental" two-click workflow.
        """
        date_str = customer.get("activity_date") or customer.get("normalized_date", "")
        if not date_str:
            print("  ⚠️ No date provided")
            return

        date_part = date_str.split()[0]
        start_dt = None
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%m-%d-%Y"]:
            try:
                start_dt = datetime.strptime(date_part, fmt)
                break
            except ValueError:
                continue

        if start_dt is None:
            print(f"  ⚠️ Cannot parse date '{date_str}' with any known format")
            return

        is_multi_day = customer.get("mpowr_activity") == "Multi-Day Adventure Rental"

        try:
            cal_found = False
            cal_btn = self._page.locator("button[aria-label='Select Date Calendar Button']").first
            
            try:
                if cal_btn.is_visible(timeout=2000):
                    cal_found = True
            except Exception:
                pass

            if not cal_found:
                cal_btn = self._page.locator("button[aria-label*='date' i], button[aria-label*='calendar' i]").first
                try:
                    if cal_btn.is_visible(timeout=2000):
                        cal_found = True
                except Exception:
                    pass

            if not cal_found:
                # If no icon, try to find the actual input by its MPOWR label
                # MPOWR might label it "Start Date" or just "Date"
                date_input = self._page.get_by_label(re.compile(r"date", re.IGNORECASE)).first
                if date_input.count() == 0:
                    date_input = self._page.get_by_role("textbox", name=re.compile(r"date", re.IGNORECASE)).first
                try:
                    if date_input.is_visible(timeout=5000):
                        if is_multi_day:
                            date_input.click()
                            cal_found = True
                        else:
                            # For regular rentals, typing directly is faster and works
                            formatted = f"{start_dt.month:02d}/{start_dt.day:02d}/{start_dt.year}"
                            date_input.click()
                            date_input.fill(formatted)
                            date_input.press("Enter")
                            print(f"  ✅ Date typed directly: {formatted}")
                            time.sleep(2)
                            return
                except Exception:
                    pass

            if not cal_found:
                raise ValueError("Calendar button or Start Date input field could not be found.")

            if not is_multi_day:
                cal_btn.click()
                time.sleep(1)

            def _navigate_and_click_calendar(target_dt: datetime, label: str):
                """Navigate a dual-month or single-month MPOWR calendar and click the target day.
                
                MPOWR uses a side-by-side dual-month calendar (e.g. April 2026 | May 2026).
                The bot reads ALL visible month headers to avoid unnecessary navigation.
                Navigation buttons use sr-only text, so get_by_role is required.
                """
                target_month = target_dt.month
                target_year = target_dt.year
                target_day = target_dt.day
                month_names = ["January", "February", "March", "April", "May", "June",
                               "July", "August", "September", "October", "November", "December"]
                target_month_name = month_names[target_month - 1]
                
                def _find_target_day_btn():
                    """Find the correct day button scoped to the target month's panel.
                    
                    In a dual-month calendar, the same day number appears in both panels.
                    We scope to the panel whose heading contains the target month name.
                    
                    MPOWR calendar HTML structure (react-day-picker):
                      <div class="rdp-months">
                        <div class="rdp-month">  ← individual month panel
                          <div class="rdp-caption">April 2026</div>
                          <table class="rdp-table">...</table>
                        </div>
                        <div class="rdp-month">  ← second month panel  
                          <div class="rdp-caption">May 2026</div>
                          <table class="rdp-table">...</table>
                        </div>
                      </div>
                    """
                    # Find all buttons matching the target day number
                    day_btns = self._page.locator(f"button:not([class*='outside'])").filter(
                        has_text=re.compile(f"^{target_day}$")
                    )
                    count = day_btns.count()
                    
                    # Iterate through them to find the one inside the correct month panel
                    for i in range(count):
                        btn = day_btns.nth(i)
                        
                        # Evaluate the closest container to see if it belongs to the target month
                        text_content = btn.evaluate("""el => {
                            let parent = el.closest('table, .rdp-month, [class*="month"], [role="grid"]');
                            if (!parent && el.parentElement && el.parentElement.parentElement) {
                                parent = el.parentElement.parentElement.parentElement;
                            }
                            return parent ? parent.innerText : '';
                        }""")
                        
                        if target_month_name in text_content and str(target_year) in text_content:
                            print(f"    Found day {target_day} in {target_month_name} panel")
                            return btn
                            
                    # Global fallback (single-month calendars where the container might not match above)
                    if count > 0:
                        first_btn = day_btns.first
                        if first_btn.is_visible():
                            print(f"    Found day {target_day} via global fallback")
                            return first_btn
                            
                    return None
                
                def _target_month_is_visible():
                    """Check if ANY visible month header already shows the target month."""
                    headers = self._page.locator("div").filter(
                        has_text=re.compile(
                            r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$"
                        )
                    )
                    count = headers.count()
                    for i in range(count):
                        try:
                            text = headers.nth(i).inner_text().strip()
                            if text == f"{target_month_name} {target_year}":
                                return True
                        except Exception:
                            continue
                    return False
                
                # Phase 1: Check if target month is already visible (handles dual-month calendars)
                if _target_month_is_visible():
                    print(f"  ✅ {label}: {target_month_name} {target_year} already visible in calendar")
                else:
                    # Phase 2: Navigate until the target month appears
                    prev_header_text = None
                    for attempt in range(24):
                        header = self._page.locator("div").filter(
                            has_text=re.compile(
                                r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$"
                            )
                        ).first
                        header_text = header.inner_text().strip() if header.is_visible() else ""
                        
                        if not header_text:
                            print(f"  ⚠️ Cannot read calendar header on attempt {attempt}")
                            break

                        if header_text == prev_header_text:
                            print(f"  ⚠️ Calendar stuck on '{header_text}' — breaking out")
                            break
                        prev_header_text = header_text

                        # Check if target is now visible (could be in either panel of dual-month)
                        if _target_month_is_visible():
                            break

                        parts = header_text.split()
                        if len(parts) == 2:
                            try:
                                current_month = month_names.index(parts[0]) + 1
                                current_year = int(parts[1])
                            except (ValueError, IndexError):
                                print(f"  ⚠️ Cannot parse calendar header: {header_text}")
                                break

                            current_total = current_year * 12 + current_month
                            target_total = target_year * 12 + target_month

                            if target_total > current_total:
                                # get_by_role correctly resolves accessible name from sr-only text
                                next_btn = self._page.get_by_role("button", name="Next month").first
                                next_btn.click(timeout=5000)
                            else:
                                prev_btn = self._page.get_by_role("button", name="Previous month").first
                                prev_btn.click(timeout=5000)
                            time.sleep(0.5)
                
                # Phase 3: Click the target day (scoped to the correct month panel)
                day_btn = _find_target_day_btn()
                
                if day_btn and day_btn.is_visible():
                    is_disabled = day_btn.evaluate("el => el.disabled || el.getAttribute('aria-disabled') === 'true' || el.getAttribute('data-disabled') === 'true'")
                    if is_disabled:
                        raise ValueError(f"Date Overbooked or Unavailable! {target_month:02d}/{target_day:02d}/{target_year} is greyed out in MPOWR.")

                    # EDGE-12 FIX: Inject a 150ms mousedown delay so React's synthetic event handler actually registers the click!
                    day_btn.click(delay=150)
                    time.sleep(0.5)
                    
                    # Failsafe: if the calendar button remains visible after selecting, fire an Enter key to lock it
                    if day_btn.is_visible():
                        day_btn.press("Enter")
                        time.sleep(0.5)

                    print(f"  ✅ {label} selected via calendar: {target_month:02d}/{target_day:02d}/{target_year}")
                    time.sleep(1)
                        
                else:
                    raise ValueError(f"{label} day '{target_day}' not found in calendar")

            # Execute Calendar Navigation
            _navigate_and_click_calendar(start_dt, "Start Date")

            if is_multi_day:
                duration_str = customer.get("ticket_duration_string", "")
                days = 2
                import re as regex
                m = regex.search(r'(\d+)\s*-?\s*day', duration_str, regex.IGNORECASE)
                if m:
                    days = int(m.group(1))
                # End date = start + (N-1) days inclusive (3-day rental from 4/15 ends 4/17)
                end_dt = start_dt + timedelta(days=days - 1)
                
                # Re-open the calendar specifically for the End Date
                end_date_input = self._page.get_by_label("End Date", exact=True).first
                if end_date_input.is_visible():
                    end_date_input.click()
                    time.sleep(1)
                    
                _navigate_and_click_calendar(end_dt, "End Date")

        except Exception as e:
            # Re-raise so the main batch loop catches it and generates a proper error screenshot
            print(f"  ⚠️ Calendar date selection failed: {e}")
            raise

    def _handle_time_selection(self, target_time: str):
        """Handle time slot selection — MPOWR uses Headless UI Listbox.

        The Start Time field is NOT a native <select>. It's a button with
        id starting with 'headlessui-listbox-button-'. Clicking it opens a
        modal dialog titled 'Start Time' with div[role='option'] items.
        Time format is lowercase like '9am', '5pm', '12pm'.
        """
        if not target_time:
            print("  ⚠️ No time provided")
            return

        # Normalize the target time from various formats to MPOWR's style
        # Input could be "10:00:00 AM", "8:30 AM", "0.3333333333", "8:30:00 AM"
        try:
            # Handle decimal time (e.g. 0.3333333333 = 8:00 AM from Google Sheets)
            if re.match(r'^\d+\.\d+$', str(target_time)):
                decimal_hours = float(target_time) * 24
                # Convert explicitly through total_minutes to avoid floating point anomalies (e.g. 14.0 hours tracking as 13.99 + 60 minutes)
                total_minutes = int(round(decimal_hours * 60))
                
                hour = total_minutes // 60
                minute = total_minutes % 60
                
                period = "am" if hour < 12 else "pm"
                if hour > 12:
                    hour -= 12
                if hour == 0:
                    hour = 12
                    
                if minute == 0:
                    normalized = f"{hour}{period}"
                else:
                    normalized = f"{hour}:{minute:02d}{period}"
            else:
                # Handle "10:00:00 AM", "8:30 AM", "10:00 AM" etc.
                clean = re.sub(r':\d{2}(?=\s)', '', str(target_time).strip())  # "10:00:00 AM" → "10:00 AM"
                clean = clean.split(",")[0].strip()
                # Try multiple time formats
                dt_time = None
                for fmt in ["%I:%M %p", "%I %p", "%I:%M%p", "%I%p", "%H:%M:%S", "%H:%M"]:
                    try:
                        dt_time = datetime.strptime(clean, fmt)
                        break
                    except ValueError:
                        continue
                if dt_time is None:
                    raise ValueError(f"Cannot parse '{clean}' with any known format")
                # Manual formatting (Windows-safe — no %-I)
                hour = dt_time.hour % 12 or 12
                period = "am" if dt_time.hour < 12 else "pm"
                if dt_time.minute == 0:
                    normalized = f"{hour}{period}"
                else:
                    normalized = f"{hour}:{dt_time.minute:02d}{period}"
        except Exception as e:
            print(f"  ⚠️ Could not normalize time '{target_time}': {e}")
            normalized = str(target_time).lower().replace(" ", "")

        print(f"  Normalized target time: {normalized}")

        # Click the Headless UI listbox button to open the time modal
        try:
            # Primary selector: Locate the exact button attached to the Start Time label
            listbox_btn = self._page.get_by_label("Start Time", exact=True).first
            
            try:
                listbox_btn.wait_for(state="visible", timeout=3000)
            except Exception:
                print("  ⚠️ Start Time input not found on page. Skipping time slot selection.")
                return
                
            if listbox_btn.is_disabled():
                print("  ✅ Start Time listbox is disabled by MPOWR (frequently occurs on Multi-Day rentals or invalid Date configs). Skipping time selection.")
                return

            listbox_btn.click(timeout=10000)
            time.sleep(1)

            # The modal opens with "Start Time" header and time options
            # Wait for options to appear
            self._page.wait_for_selector("[role='option']", timeout=5000)

            # Collect all available time options
            options = self._page.locator("[role='option']")
            option_count = options.count()
            available_times = []
            for i in range(option_count):
                text = options.nth(i).inner_text().strip().lower()
                available_times.append(text)

            print(f"  Available times: {available_times}")

            # Try exact match
            for i in range(option_count):
                text = options.nth(i).inner_text().strip().lower()
                if text == normalized.lower():
                    options.nth(i).click()
                    print(f"  ✅ Start Time selected: {text}")
                    time.sleep(1)
                    return

            # Try substring/fuzzy match
            for i in range(option_count):
                text = options.nth(i).inner_text().strip().lower()
                if normalized.lower() in text or text in normalized.lower():
                    options.nth(i).click()
                    print(f"  ✅ Start Time selected (fuzzy): {text}")
                    time.sleep(1)
                    return

            # No match — use select_best_time_slot logic and pick closest ≤ target
            from data_mapper import select_best_time_slot
            best = select_best_time_slot(available_times, normalized)
            if best:
                for i in range(option_count):
                    text = options.nth(i).inner_text().strip().lower()
                    if text == best.lower():
                        options.nth(i).click()
                        print(f"  ⚠️ Used nearest time: {text} (target was {normalized})")
                        time.sleep(1)
                        return

            # Ultimate fallback: pick first available
            if option_count > 0:
                first_text = options.first.inner_text().strip()
                options.first.click()
                print(f"  ⚠️ No match for '{normalized}'. Selected first available: {first_text}")
                time.sleep(1)
                return

            # Close modal if no option selected
            close_btn = self._page.locator("button").filter(has_text="×").first
            if close_btn.is_visible():
                close_btn.click()
            print(f"  ❌ No time options available")

        except Exception as e:
            print(f"  ⚠️ Time selection error: {e}")
        finally:
            self._screenshot(f"DIAG_AFTER_TIME_SELECTION")

    def _handle_vehicle_selection(self, vehicle_name: str, qty: str):
        """Sets the quantity dropdown for the specific vehicle card auto-loaded by MPOWR.
        
        CRITICAL: Uses exact=True text matching to prevent 'RZR PRO S' from
        matching 'RZR PRO S4'. Falls back to regex word-boundary matching.
        """
        if not vehicle_name:
            print("  ⚠️ No vehicle mapped")
            return

        try:
            # Strategy: Find DIVs that contain BOTH the exact vehicle name AND a <select>.
            # Use exact=True first to prevent "RZR PRO S" from matching "RZR PRO S4"
            
            # Primary: exact match (prevents "RZR PRO S" from matching "RZR PRO S4")
            text_locator = self._page.get_by_text(vehicle_name, exact=True).first
            
            try:
                # Wait up to 5 seconds for the exact match to appear
                text_locator.wait_for(state="visible", timeout=5000)
            except Exception:
                # Fallback: regex with NEGATIVE LOOKAHEAD to prevent partial matches
                # "RZR PRO S" must NOT be followed by alphanumeric chars (e.g. "4" in "S4")
                pattern = re.compile(
                    r'\b' + re.escape(vehicle_name) + r'(?![A-Za-z0-9])',
                    re.IGNORECASE
                )
                text_locator = self._page.get_by_text(pattern).first
                try:
                    text_locator.wait_for(state="visible", timeout=3000)
                except Exception:
                    # Last resort: substring (may be inaccurate)
                    text_locator = self._page.get_by_text(vehicle_name, exact=False).first
                    try:
                        text_locator.wait_for(state="visible", timeout=3000)
                    except Exception:
                        print(f"  ❌ Vehicle card '{vehicle_name}' not found on page")
                        return

            # Find the card wrapper that contains both the text AND a select dropdown
            cards = self._page.locator("div").filter(
                has=text_locator.first
            ).filter(
                has=self._page.locator("select")
            )
            
            # The 'last' element is the deepest nested div (the card wrapper itself)
            card = cards.last
            if card.is_visible():
                select_el = card.locator("select").first
                
                if select_el.input_value() != qty:
                    select_el.select_option(value=qty)
                    print(f"  ✅ Set {vehicle_name} quantity to {qty}")
                    
                    # Dismiss any AdventureAssure modal that triggers on quantity change
                    time.sleep(1)
                    self._page.keyboard.press("Escape")
                else:
                    print(f"  ✅ {vehicle_name} quantity already {qty}")
                return
            
            print(f"  ❌ Failed to locate the quantity dropdown next to {vehicle_name}")
            
        except Exception as e:
            print(f"  ❌ Vehicle selection error: {e}")

    def _handle_insurance_selection(self, insurance_label: str):
        """Select AdventureAssure insurance via the MPOWR modal.

        Flow: Click 'Choose AdventureAssure' card → modal with two FREE options
        → click the matching option (Standard or Upgraded).
        """
        if not insurance_label:
            return

        try:
            # Click the "Choose AdventureAssure" card to open the modal
            assure_card = self._page.get_by_text("Choose AdventureAssure", exact=False).first
            try:
                assure_card.wait_for(state="visible", timeout=2000)
            except Exception:
                print("  ⚠️ AdventureAssure card not found on this listing")
                return
                
            assure_card.click()
            time.sleep(1)

            # Click the desired insurance option in the modal
            option = self._page.get_by_text(insurance_label, exact=False).first
            try:
                option.wait_for(state="visible", timeout=2000)
                option.click()
                print(f"  ✅ Insurance selected: {insurance_label}")
                time.sleep(0.5)
                # Close the modal — press Escape or click the × button
                self._page.keyboard.press("Escape")
                time.sleep(0.5)
            except Exception:
                print(f"  ❌ Failed to find insurance option: {insurance_label}")
                self._page.keyboard.press("Escape")
        except Exception as e:
            print(f"  ⚠️ Insurance selection issue: {e}")

    def _handle_guide_addons(self, guide_addons: list):
        """Select guide add-on(s) for tours. Supports MIXED guide types.

        A single reservation may need multiple different guide services.
        Example: 3 XP4 S on Hell's Revenge could need:
            - 2x "Gateway Party of 1-2 - Guide Services" ($159 each)
            - 1x "Gateway Party of 3 - 4 Guide Services" ($229)

        Strategy:
        1. Search for "Guide" in the Rental Add-Ons search to show all options
        2. For each guide type, click its specific "Add" button N times (quantity)
           - MPOWR buttons have aria-label like: "Add Gateway Party of 1-2 - Guide Services"
           - Each click adds 1 to the quantity
        3. Clear the search when done

        Args:
            guide_addons: List of {"label": "guide label", "quantity": N}
        """
        if not guide_addons:
            return

        try:
            # Scroll to the Rental Add-Ons section
            addon_section = self._page.get_by_text("Rental Add-Ons", exact=False).first
            try:
                addon_section.wait_for(state="visible", timeout=2000)
                addon_section.scroll_into_view_if_needed()
                time.sleep(0.5)
            except Exception:
                pass

            # Track which guides we still need to add (vs ones already auto-added)
            guides_to_add = []

            for guide in guide_addons:
                label = guide["label"]
                quantity = guide["quantity"]

                # Check if this guide is ACTUALLY present as an interactive Cart item (not just plain text)
                guide_card = self._page.locator("div").filter(
                    has=self._page.get_by_text(label, exact=False)
                ).filter(
                    has=self._page.locator("button").filter(has_text="+")
                ).last
                
                plus_btn = guide_card.locator("button").filter(has_text="+").first
                
                if plus_btn.is_visible():
                    print(f"  ✅ Guide add-on already in cart: {label}")
                    if quantity > 1:
                        # Assuming it auto-loaded at quantity=1
                        for _ in range(quantity - 1):
                            plus_btn.click()
                            time.sleep(2.0)  # Wait for React to process the cart update
                        print(f"  ✅ Guide quantity increased to {quantity}")
                else:
                    guides_to_add.append(guide)

            # If all guides were auto-added, we're done
            if not guides_to_add:
                return

            # Search for guides via the quick search box
            search_input = self._page.locator("input[placeholder*='find rental add-ons']").first
            if not search_input.is_visible():
                print("  ⚠️ Rental Add-Ons search not visible")
                return

            # Search "Guide" to display all guide options
            search_input.fill("Guide")
            time.sleep(1.5)

            # Add each guide type by clicking its specific "Add" button
            for guide in guides_to_add:
                label = guide["label"]
                quantity = guide["quantity"]

                add_btn = self._find_guide_add_button(label)

                if add_btn and add_btn.is_visible():
                    # Click "Add" button for the FIRST unit
                    add_btn.click()
                    print(f"  ✅ Guide add-on added: {label} (1/{quantity})")
                    time.sleep(2.0)

                    # For quantity > 1, click "Add" again for each additional unit
                    # (Each click of "Add" increments quantity by 1, or we can use +)
                    if quantity > 1:
                        for i in range(quantity - 1):
                            # Re-find the Add button (it's still in the search results)
                            add_btn = self._find_guide_add_button(label)
                            if add_btn and add_btn.is_visible():
                                add_btn.click()
                                print(f"  ✅ Guide add-on incremented: {label} ({i+2}/{quantity})")
                                time.sleep(2.0)
                            else:
                                # Fallback: try the + button on the added card below
                                guide_card = self._page.locator("div").filter(
                                    has=self._page.get_by_text(label, exact=False)
                                ).filter(
                                    has=self._page.locator("button").filter(has_text="+")
                                ).last
                                plus_btn = guide_card.locator("button").filter(has_text="+").first
                                if plus_btn.is_visible():
                                    plus_btn.click()
                                    print(f"  ✅ Guide incremented via +: {label} ({i+2}/{quantity})")
                                    time.sleep(2.0)
                else:
                    print(f"  ⚠️ Guide add-on '{label}' not found in search results")

            # Clear the search
            search_input.clear()
            time.sleep(0.5)

        except Exception as e:
            print(f"  ⚠️ Guide add-on error: {e}")

    def _find_guide_add_button(self, label: str):
        """Find the specific 'Add' button for a guide service by aria-label.

        MPOWR buttons have aria-labels like:
            aria-label="Add Gateway Party of 1-2 - Guide Services"
            aria-label="Add Pro R Hell's Revenge Guide Services"

        Handles straight vs curly apostrophe variants.

        Returns:
            Playwright Locator for the button, or None if not found
        """
        # Try exact match first
        add_label = f"Add {label}"
        add_btn = self._page.get_by_role("button", name=add_label, exact=True)
        if add_btn.count() > 0:
            return add_btn

        # Fallback: try curly apostrophe
        if "'" in label:
            curly_label = label.replace("'", "\u2019")
            add_btn = self._page.get_by_role("button", name=f"Add {curly_label}", exact=True)
            if add_btn.count() > 0:
                return add_btn

        # Fallback: try straight apostrophe
        if "\u2019" in label:
            straight_label = label.replace("\u2019", "'")
            add_btn = self._page.get_by_role("button", name=f"Add {straight_label}", exact=True)
            if add_btn.count() > 0:
                return add_btn

        # Final fallback: non-exact match
        add_btn = self._page.get_by_role("button", name=add_label, exact=False)
        if add_btn.count() > 0:
            return add_btn

        return None

    # EDGE-3: Whitelist of known mandatory checkbox keywords.
    # Only check boxes matching these — prevents auto-checking promotional/optional boxes.
    MANDATORY_CHECKBOX_KEYWORDS = [
        "driver minimum age",
        "age requirement",
        "25 years",
        "ohv",
        "vehicle education",
        "mandatory",
        "acknowledge",
        "agree to the terms",
        "overnight",
        "parked by",
        "10:00",
        "quiet hours",
        "i understand",
        "i agree",
        "i accept",
    ]

    # BLOCKLIST: Listing names in MPOWR that should NEVER be selected by the bot.
    # These are special events, meetups, or promotional listings with no valid
    # booking calendar. If the bot selects one, it will crash on date selection.
    # Matching is case-insensitive substring — any card whose text contains one
    # of these phrases will be skipped.
    SPECIAL_EVENT_BLOCKLIST = [
        "meet up",
        "meetup",
        "network",
        "special event",
        "demo day",
        "charity",
        "fundraiser",
    ]

    def _handle_additional_questions(self):
        """Checks required checkboxes in the 'Additional Questions' section.

        EDGE-3 FIX: Uses a keyword whitelist instead of checking ALL checkboxes.
        Only checks boxes whose labels match known mandatory agreement phrases.

        Known mandatory checkboxes for rental activities:
        - 'Driver minimum age requirement: 25 years of age or older.'
        - 'MANDATORY UTAH OHV VEHICLE EDUCATION COURSE'

        Tours show 'No additional questions for this product' — nothing to check.
        The SMS consent checkbox at the bottom is always excluded.
        """
        try:
            # First check if there's a "No additional questions" message
            no_questions = self._page.get_by_text("No additional questions for this product", exact=False).first
            if no_questions.is_visible():
                print("  ✅ No additional questions for this activity.")
                return

            # Find checkboxes specifically within the Additional Questions area
            checkboxes = self._page.locator("input[type='checkbox']")
            count = checkboxes.count()
            checked_count = 0
            skipped_count = 0

            for i in range(count):
                cb = checkboxes.nth(i)
                if cb.is_visible() and not cb.is_checked():
                    # Get the associated label text by ascending the DOM until we find readable text
                    try:
                        parent_text = cb.evaluate("""el => {
                            let curr = el;
                            while(curr && curr.innerText.trim().length < 5 && curr !== document.body) {
                                curr = curr.parentElement;
                            }
                            return curr ? curr.innerText.trim() : '';
                        }""")
                    except Exception:
                        parent_text = ""

                    parent_lower = parent_text.lower()

                    # Always skip SMS consent
                    if "sms" in parent_lower or "text message" in parent_lower:
                        continue

                    # EDGE-3: Only check if label matches a known mandatory keyword
                    is_mandatory = any(kw in parent_lower for kw in self.MANDATORY_CHECKBOX_KEYWORDS)

                    if is_mandatory:
                        try:
                            # Playwright check() ensures the state changes, but fails if React intercepts it weirdly
                            cb.check(timeout=1500)
                        except Exception:
                            try:
                                cb.check(force=True, timeout=1500)
                            except Exception:
                                # Fallback: clicking the parent element (usually the label) often bypasses React checkbox interception
                                cb.locator("..").click(force=True)
                                
                        checked_count += 1
                        if parent_text:
                            print(f"    ☑️ Checked: {parent_text[:60]}...")
                        time.sleep(0.1)
                    else:
                        skipped_count += 1
                        if parent_text:
                            print(f"    ⏭️ Skipped non-mandatory: {parent_text[:60]}...")

            if checked_count > 0:
                print(f"  ✅ Checked {checked_count} mandatory agreement box(es). Skipped {skipped_count} optional.")
            else:
                print(f"  ✅ All mandatory boxes already checked. Skipped {skipped_count} optional.")
        except Exception as e:
            print(f"  ⚠️ Error handling additional questions: {e}")

    # -----------------------------------------------------------------------
    # Batch Processing
    # -----------------------------------------------------------------------

    def create_batch(self, customers: list[dict]) -> list[CreationResult]:
        """
        Creates multiple reservations in a single browser session.
        Logs in once, then processes each customer sequentially.

        Production safeguards:
        - Duplicate detection: checks MPOWR for existing webhook email before creating
        - Session health: verifies session every 5 reservations, re-auths if expired
        - Structured logging: all actions logged to both console and JSON log file

        Args:
            customers: List of dicts from data_mapper.build_customer_payload_from_row()

        Returns:
            List of CreationResult objects (one per customer)
        """
        if not customers:
            log.info("[Creator Bot] No customers to process.")
            return []

        results = []
        created = 0
        failed = 0
        skipped = 0
        duplicates = 0
        consecutive_failures = 0  # Track consecutive failures for circuit breaker

        try:
            log.info(f"\n[Creator Bot] Starting batch of {len(customers)} reservation(s)...")
            self._start_browser()

            for i, customer in enumerate(customers):
                tw_conf = customer.get("tw_confirmation", "?")
                name = f"{customer.get('first_name', '?')} {customer.get('last_name', '?')}"
                ctx = {"tw_conf": tw_conf, "name": name, "index": f"{i+1}/{len(customers)}"}

                log.info(f"\n--- Reservation {i+1}/{len(customers)} ---",
                         extra={"ctx": ctx})

                # --- Circuit Breaker: abort if too many consecutive failures ---
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    log.error(
                        f"[Circuit Breaker] {MAX_CONSECUTIVE_FAILURES} consecutive failures. "
                        f"Aborting remaining {len(customers) - i} reservation(s).",
                        extra={"ctx": ctx}
                    )
                    self.slack.send_error_alert(
                        customer_name="BATCH ABORT",
                        activity_date="N/A",
                        activity="N/A",
                        vehicle_type="N/A",
                        error_reason=(
                            f"Circuit breaker: {MAX_CONSECUTIVE_FAILURES} consecutive failures. "
                            f"Remaining {len(customers) - i} reservation(s) skipped. "
                            f"Please investigate and restart."
                        ),
                    )
                    for remaining in customers[i:]:
                        results.append(CreationResult(
                            status="error",
                            error_message="Batch aborted: circuit breaker triggered"
                        ))
                        failed += 1
                    break

                # --- Session Health Check (every 5 reservations) ---
                if i > 0 and i % 5 == 0:
                    log.info("[Session] Performing periodic session health check...",
                             extra={"ctx": ctx})
                    if not self._is_session_alive():
                        if not self._reauth():
                            log.error("[Session] Re-auth failed — aborting remaining batch",
                                      extra={"ctx": ctx})
                            self.slack.send_error_alert(
                                customer_name="SESSION FAILURE",
                                activity_date="N/A",
                                activity="N/A",
                                vehicle_type="N/A",
                                error_reason="MPOWR session expired and re-authentication failed. Batch aborted.",
                            )
                            for remaining in customers[i:]:
                                results.append(CreationResult(
                                    status="error",
                                    error_message="Session expired and re-auth failed"
                                ))
                                failed += 1
                            break

                # --- Data Validation ---
                if customer.get("error"):
                    error_msg = customer["error"]
                    log.error(f"  ❌ Data mapping error: {error_msg}",
                              extra={"ctx": ctx})
                    self.slack.send_error_alert(
                        customer_name=name,
                        activity_date=customer.get("activity_date", "?"),
                        activity=customer.get("activity", "?"),
                        vehicle_type=customer.get("mpowr_vehicle", "?"),
                        error_reason=error_msg,
                        tw_confirmation=tw_conf,
                    )
                    results.append(CreationResult(status="error", error_message=error_msg))
                    failed += 1
                    # Data errors don't count as consecutive failures (not bot issue)
                    continue

                # --- Duplicate Detection (skip in dry_run mode) ---
                if not self.dry_run:
                    webhook_email = customer.get("webhook_email", "")
                    existing_id = self._check_for_duplicate(webhook_email)
                    if existing_id:
                        log.warning(
                            f"  ⚠️ DUPLICATE DETECTED: {name} already exists as MPOWR #{existing_id}. Skipping.",
                            extra={"ctx": {**ctx, "existing_mpowr_id": existing_id}}
                        )
                        self.slack.send_duplicate_alert(
                            customer_name=name,
                            tw_confirmation=tw_conf,
                            existing_mpowr_id=existing_id,
                            activity=customer.get("activity", "?"),
                            activity_date=customer.get("activity_date", "?"),
                        )
                        results.append(CreationResult(
                            status="duplicate",
                            mpowr_conf_id=existing_id,
                            error_message=f"Duplicate: already exists as #{existing_id}",
                        ))
                        duplicates += 1
                        consecutive_failures = 0  # Reset on successful detection
                        continue

                # --- Create the reservation ---
                try:
                    result = self.create_reservation(customer)
                except Exception as e:
                    log.error(f"  ❌ Unhandled error during creation: {e}",
                              extra={"ctx": ctx})
                    result = CreationResult(
                        status="error",
                        error_message=f"Unhandled: {str(e)}",
                        screenshot_path=self._screenshot(f"error_unhandled_{tw_conf}"),
                    )

                results.append(result)
                log.info(f"  Result: {result.status}",
                         extra={"ctx": {**ctx, "status": result.status,
                                        "mpowr_id": result.mpowr_conf_id}})

                if result.status == "success":
                    created += 1
                    consecutive_failures = 0  # Reset on success

                    # --- Slack: notify on EVERY successful creation ---
                    self.slack.send_reservation_success(
                        customer_name=name,
                        tw_confirmation=tw_conf,
                        activity=customer.get("activity", "?"),
                        vehicle_type=customer.get("mpowr_vehicle", "?"),
                        mpowr_conf_id=result.mpowr_conf_id,
                        activity_date=customer.get("activity_date", "?"),
                        activity_time=customer.get("activity_time", "?"),
                        vehicle_qty=customer.get("vehicle_qty", 1),
                        target_price=customer.get("target_price", 0.0),
                        screenshot_path=result.screenshot_path,
                    )

                elif result.status == "dry_run":
                    skipped += 1
                    consecutive_failures = 0  # Dry runs are not failures

                    # --- Slack: notify on dry runs too ---
                    self.slack.send_dry_run_alert(
                        customer_name=name,
                        tw_confirmation=tw_conf,
                        activity=customer.get("activity", "?"),
                        vehicle_type=customer.get("mpowr_vehicle", "?"),
                        activity_date=customer.get("activity_date", "?"),
                        activity_time=customer.get("activity_time", "?"),
                        screenshot_path=result.screenshot_path,
                    )

                elif result.status == "error":
                    failed += 1
                    consecutive_failures += 1

                    # Check if this error might be a session issue
                    if result.error_message and ("timeout" in result.error_message.lower()
                                                  or "navigation" in result.error_message.lower()):
                        log.warning("[Session] Error may indicate session issue. Checking...",
                                    extra={"ctx": ctx})
                        if not self._is_session_alive():
                            if self._reauth():
                                log.info("[Session] Re-authenticated successfully. Continuing batch.")
                                consecutive_failures = 0  # Reset after successful re-auth
                            else:
                                log.error("[Session] Re-auth failed after error. Aborting remaining.")
                                self.slack.send_error_alert(
                                    customer_name="SESSION FAILURE",
                                    activity_date="N/A",
                                    activity="N/A",
                                    vehicle_type="N/A",
                                    error_reason="Session expired and re-auth failed after error.",
                                )
                                break

                    # --- Slack: error alert with screenshot ---
                    self.slack.send_error_alert(
                        customer_name=name,
                        activity_date=customer.get("activity_date", "?"),
                        activity=customer.get("activity", "?"),
                        vehicle_type=customer.get("mpowr_vehicle", "?"),
                        error_reason=result.error_message or "Unknown error",
                        screenshot_path=result.screenshot_path,
                        tw_confirmation=tw_conf,
                    )

                # Cooldown between reservations (with exponential backoff on failures)
                if i < len(customers) - 1:
                    cooldown = TIMEOUTS["between_reservations"]
                    if consecutive_failures > 0:
                        # Exponential backoff: 3s, 6s, 12s on consecutive failures
                        cooldown = cooldown * (2 ** consecutive_failures)
                        log.warning(f"  ⏳ Extended cooldown ({cooldown}ms) due to {consecutive_failures} consecutive failure(s)")
                    else:
                        log.debug(f"  ⏳ Cooldown ({cooldown}ms)...")
                    time.sleep(cooldown / 1000)

        except MpowrLoginError as e:
            log.critical(f"\n❌ Login failed — aborting entire batch: {e}")
            self.slack.send_error_alert(
                customer_name="BATCH",
                activity_date="N/A",
                activity="N/A",
                vehicle_type="N/A",
                error_reason=f"MPOWR Login Failed — entire batch aborted: {e}",
            )
        except Exception as e:
            log.critical(f"\n❌ Unexpected batch error: {e}")
            self.slack.send_error_alert(
                customer_name="BATCH",
                activity_date="N/A",
                activity="N/A",
                vehicle_type="N/A",
                error_reason=f"Unexpected batch error: {e}",
            )
        finally:
            self._close_browser()

        # Post summary
        self.slack.send_success_summary(created, failed, skipped, duplicates)
        log.info(
            f"\n[Creator Bot] Batch complete: {created} created, {failed} failed, "
            f"{skipped} dry_run, {duplicates} duplicates skipped"
        )

        return results

    # -----------------------------------------------------------------------
    # Duplicate Detection
    # -----------------------------------------------------------------------

    def _check_for_duplicate(self, webhook_email: str) -> str | None:
        """Check if a reservation with this webhook email already exists in MPOWR.

        The webhook email (e.g. polaris+CO-D5A-8KY@epic4x4adventures.com) is
        UNIQUE per TripWorks confirmation — if we find it in MPOWR's order list,
        the reservation was already created (possibly by a previous run that
        crashed before writing back the confirmation ID).

        Strategy:
        1. Navigate to MPOWR Reservations List
        2. Use the search/filter to look for the webhook email
        3. If a matching reservation row is found, extract its MPOWR ID

        Args:
            webhook_email: The polaris+{tw_conf}@epic4x4adventures.com email

        Returns:
            MPOWR confirmation ID string if duplicate found, None otherwise
        """
        if not webhook_email:
            return None

        try:
            log.debug(f"  [Duplicate Check] Searching for: {webhook_email}")

            # Navigate to the reservations list
            self._page.goto("https://mpwr-hq.poladv.com/orders",
                           timeout=TIMEOUTS["create_page_load"],
                           wait_until="domcontentloaded")
            time.sleep(2)

            # Look for a search input on the reservations list page
            search_input = self._page.locator(
                "input[placeholder*='search' i], input[placeholder*='filter' i], "
                "input[type='search']"
            ).first

            if search_input.count() > 0 and search_input.is_visible():
                # Use the search box to filter by webhook email
                search_input.fill(webhook_email)
                time.sleep(2)

                # Check if any results appear — look for order links excluding the 'create' button
                order_links = self._page.locator("a[href*='/orders/']:not([href*='create'])")
                if order_links.count() > 0:
                    href = order_links.first.get_attribute("href")
                    if href:
                        match = re.search(r'/orders/([A-Za-z0-9-]+)', href)
                        if match:
                            found_id = match.group(1)
                            log.info(f"  [Duplicate Check] Found existing #{found_id}")
                            search_input.clear()
                            time.sleep(0.5)
                            return found_id

                # Clear search
                search_input.clear()
                time.sleep(0.5)
            else:
                # Fallback: scan page HTML directly for the webhook email
                page_html = self._page.content().lower()
                if webhook_email.lower() in page_html:
                    log.warning("  [Duplicate Check] Email found in page HTML (no search box)")
                    links = self._page.eval_on_selector_all(
                        "a[href*='/orders/']",
                        "els => els.map(e => ({href: e.href, text: e.textContent}))"
                    )
                    for link in links:
                        link_match = re.search(r'/orders/(\d+)', link.get("href", ""))
                        if link_match:
                            return link_match.group(1)

            return None

        except Exception as e:
            # On error, proceed with creation (safer than blocking)
            log.warning(f"  [Duplicate Check] Error (non-fatal, proceeding): {e}")
            return None

    # -----------------------------------------------------------------------
    # Payment Management (settle_payment only — cancel/update moved to MPWR_Update_Cancel_Agent)
    # -----------------------------------------------------------------------



    def settle_payment(self, mpwr_id: str) -> bool:
        """Settle an existing balance in MPOWR using Cash."""
        try:
            log.info(f"[Creator Bot] Settling Cash Payment for MPWR {mpwr_id}...")
            if not self._browser or not self._is_session_alive():
                self._start_browser()

            mpwr_url = f"https://mpwr-hq.poladv.com/orders/{mpwr_id}"
            self._page.goto(mpwr_url, timeout=TIMEOUTS["create_page_load"], wait_until="domcontentloaded")
            time.sleep(4)

            # Look for Make Payment inside the payment box, or Actions -> Add Card On File
            actions_btn = self._page.locator("button:has-text('Actions')").first
            if actions_btn.is_visible():
                actions_btn.click()
                time.sleep(1)
            
            # Since Tripworks undocumented Payments are confusing in MPOWR, we click "New Charge" or "Settle"
            charge_btn = self._page.get_by_text("New Charge", exact=False).first
            if charge_btn.is_visible():
                charge_btn.click()
                time.sleep(2)
            else:
                # Close dropdown, fallback to Make Payment
                self._page.keyboard.press("Escape")
                
            make_payment_btn = self._page.get_by_text("Make Payment", exact=False).first
            if make_payment_btn.is_visible():
                make_payment_btn.click()
                time.sleep(2)

            # Select Cash
            cash_option = self._page.get_by_text("Cash", exact=True).first
            if cash_option.is_visible():
                cash_option.click()
                time.sleep(1)

            submit_btn = self._page.get_by_text("Collect", exact=False).first
            if self.dry_run:
                log.info(f"DRY RUN: Would have collected cash for {mpwr_id}")
            else:
                submit_btn.click()
                time.sleep(3)
                log.info(f"✅ Successfully Settled Payment for {mpwr_id} in MPOWR")

            self._close_browser()
            return True
            
        except Exception as e:
            log.error(f"Failed to settle payment for {mpwr_id}: {e}")
            self._screenshot(f"error_payment_{mpwr_id}")
            self._close_browser()
            return False




# ---------------------------------------------------------------------------
# Maintenance Utilities
# ---------------------------------------------------------------------------

def reap_playwright_zombies():
    """Kill lingering headless msedge.exe/chrome.exe processes spawned by Playwright.
    
    Prevents zombie processes from consuming system RAM if the bot crashes or is force-quit.
    Specifically targets processes with 'ms-playwright' in their launch path to avoid
    killing the user's personal browser sessions. Zero-dependency via PowerShell.
    """
    import subprocess
    script = "Get-CimInstance Win32_Process -Filter \"Name = 'msedge.exe' OR Name = 'chrome.exe'\" | Where-Object {$_.ExecutablePath -match 'ms-playwright'} | Stop-Process -Force"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
        # Suppress output; logging would be noisy since it checks every 5 mins
    except Exception as e:
        log.warning(f"Failed to execute zombie Playwright reaper: {e}")

def cleanup_old_screenshots(max_age_days: int = 7):
    """Delete screenshot files older than max_age_days.

    Prevents unbounded storage growth (~60 MB/day at full capacity).
    Called by the scheduler in main.py once per day.

    Args:
        max_age_days: Delete files older than this many days (default 7)
    """
    import glob
    from pathlib import Path

    cutoff = time.time() - (max_age_days * 86400)
    deleted = 0
    errors = 0

    # LOW-4 FIX: Clean up all image formats, not just PNG
    for f in glob.glob(os.path.join(SCREENSHOT_DIR, "*.*")):
        try:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
                deleted += 1
        except Exception as e:
            errors += 1

    if deleted > 0 or errors > 0:
        log.info(f"[Cleanup] Deleted {deleted} screenshots older than {max_age_days} days. Errors: {errors}")
