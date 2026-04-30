import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(r'C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent\.env')
load_dotenv(env_path)
sys.path.append(r'C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent')

from mpowr_updater_bot import MpowrUpdaterBot
import os
bot = MpowrUpdaterBot(os.getenv('MPOWR_EMAIL'), os.getenv('MPOWR_PASSWORD'), dry_run=True)
bot._reauth()

# Go directly to Reschedule page
bot._page.goto('https://mpwr-hq.poladv.com/orders/CO-P7Y-2DM/reschedule', wait_until='domcontentloaded')
import time
time.sleep(5)

html = bot._page.content()
with open('reschedule_page.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML saved to reschedule_page.html')

buttons = bot._page.locator('button').all()
for i, btn in enumerate(buttons):
    try:
        text = btn.inner_text(timeout=1000).strip().replace('\n', ' ')
        if text:
            print(f'Button {i}: {text}')
    except Exception:
        pass

bot._close_browser()
