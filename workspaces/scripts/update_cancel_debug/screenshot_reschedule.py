import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(r'C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent\.env')
load_dotenv(env_path)
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent')

from mpowr_updater_bot import MpowrUpdaterBot
import os
import time

bot = MpowrUpdaterBot(os.getenv('MPOWR_EMAIL'), os.getenv('MPOWR_PASSWORD'), dry_run=True)
bot._reauth()

# Go directly to Reschedule page
bot._page.goto('https://mpwr-hq.poladv.com/orders/CO-P7Y-2DM/reschedule', wait_until='domcontentloaded')
time.sleep(5)

bot._screenshot("pre_click_listing")

# Find listing button and click it
import re
listing_btn = bot._page.locator("button").filter(
    has_text=re.compile("Choose Listing|Hell|Poison|Moab|Hour|Half-Day|Full-Day|Multi-Day|Slingshot|Revenge|Spider|Discovery")
).first

if listing_btn.count() > 0:
    print("Clicking listing button!")
    listing_btn.click()
    time.sleep(2)
    bot._screenshot("post_click_listing")
    
    # Try to find Apply button
    apply_btn = bot._page.get_by_role("button", name="Apply")
    if apply_btn.count() > 0:
        print("Apply button found! Clicking it...")
        apply_btn.click()
        time.sleep(2)
        bot._screenshot("post_click_apply")
else:
    print("Listing button not found!")

bot._close_browser()
