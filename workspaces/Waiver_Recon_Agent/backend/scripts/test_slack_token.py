import os
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
# Load .env from root directory!
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', '.env'))

from slack_notifier import SlackNotifier

slack = SlackNotifier()
print(f"Token loaded: {slack.bot_token[:10] if slack.bot_token else 'NONE'}")

# Generate a fast blank screenshot to upload
img_path = "test_ss.png"
with open(img_path, "wb") as f:
    f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')

print("Sending test error message with screenshot attachment...")
slack.send_error_alert("Test Customer", "TW-1234", "Test Activity", "Test Vehicle", "2026-05-15", "test error", img_path)

if os.path.exists(img_path):
    os.remove(img_path)

print("Test complete. Check Slack!")
