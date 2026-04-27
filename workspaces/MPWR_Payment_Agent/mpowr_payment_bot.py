import os
import time
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
from bot_logger import get_bot_logger
from slack_notifier import slack
from mpowr_login import login_to_mpowr, MpowrLoginError

log = get_bot_logger()

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
HEADLESS = os.getenv("CREATOR_HEADLESS", "true").lower() == "true"

def take_screenshot(page: Page, name: str) -> str:
    os.makedirs("screenshots", exist_ok=True)
    filename = f"screenshots/{name}_{int(time.time())}.png"
    try:
        page.screenshot(path=filename, full_page=True)
        return filename
    except Exception as e:
        log.error(f"Failed to take screenshot: {e}")
        return None

def process_settlement(mpwr_id: str, tw_conf: str, amount_due: float) -> bool:
    """
    Logs into MPOWR and settles the balance using cash.
    Returns True if successful or already settled, False on error.
    """
    email = os.getenv("MPOWR_EMAIL")
    password = os.getenv("MPOWR_PASSWORD")
    
    if not email or not password:
        log.error("MPOWR credentials not set in .env")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(viewport={"width": 1280, "height": 1024})
        page = context.new_page()

        try:
            # Login
            login_to_mpowr(page, email, password)

            # Navigate to order
            order_url = f"https://mpwr-hq.poladv.com/orders/{mpwr_id}"
            log.info(f"Navigating to {order_url}")
            page.goto(order_url, timeout=30000)
            page.wait_for_selector('h1:has-text("Reservation Details")', state='attached', timeout=15000)

            # Check if balance is already 0
            # Wait a moment for dynamic data to load
            time.sleep(3)
            
            # Check for the Settle Balance button
            # It appears next to "Amount Due" when there is a balance
            settle_btn_locator = page.locator('text="Settle Balance"').first
            
            try:
                settle_btn_locator.wait_for(state="visible", timeout=5000)
                has_settle_btn = True
            except PlaywrightTimeoutError:
                has_settle_btn = False

            if not has_settle_btn:
                log.info(f"[{tw_conf}] No 'Settle Balance' button found. Assuming already settled or $0 due.")
                # We can consider it settled for our purposes
                return True

            log.info(f"[{tw_conf}] Found 'Settle Balance' button. Proceeding with cash settlement.")
            
            if DRY_RUN:
                log.info(f"[{tw_conf}] DRY RUN: Skipping actual settlement clicks.")
                slack.send_message(f"🧪 DRY RUN: Would have settled ${amount_due:.2f} for TW {tw_conf} (MPOWR #{mpwr_id})")
                return True

            # 1. Click blue Settle Balance button next to Amount Due
            settle_btn_locator.click()
            time.sleep(1)

            # 2. Click "Settle Balance" button in the flyout/modal
            # Look for button in a dialog
            modal_settle_btn = page.locator('div[role="dialog"] button:has-text("Settle Balance")').first
            modal_settle_btn.wait_for(state="visible", timeout=5000)
            modal_settle_btn.click()
            time.sleep(2)

            # 3. In the Payment modal, click "Cash / Check" tab
            cash_check_tab = page.locator('text="Cash / Check"').first
            cash_check_tab.wait_for(state="visible", timeout=5000)
            cash_check_tab.click()
            time.sleep(1)

            # 4. Select "Cash" option (might be a radio or a div)
            cash_option = page.locator('text="Customer has paid the charge amount in cash."').first
            cash_option.click()
            time.sleep(1)

            # 5. Click the "Charge $X.XX" button
            charge_btn = page.locator('button:has-text("Charge $")').first
            charge_btn.click()
            
            # Wait for success / modal to close
            time.sleep(3)
            log.info(f"[{tw_conf}] Payment settled successfully in MPOWR.")
            slack.send_payment_success(tw_conf, mpwr_id, amount_due)
            return True

        except Exception as e:
            err_msg = str(e)
            log.error(f"Failed to settle payment for {tw_conf}: {err_msg}")
            screenshot = take_screenshot(page, f"payment_error_{tw_conf}")
            slack.send_error_alert("Settle Payment", tw_conf, mpwr_id, err_msg, screenshot)
            return False
        finally:
            browser.close()
