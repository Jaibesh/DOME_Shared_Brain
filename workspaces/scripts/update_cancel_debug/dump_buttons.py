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

bot._page.goto('https://mpwr-hq.poladv.com/orders/CO-P7Y-2DM', wait_until='domcontentloaded')
import time
time.sleep(5)

html = bot._page.content()
with open('details_page.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML saved to details_page.html')

bot._close_browser()
