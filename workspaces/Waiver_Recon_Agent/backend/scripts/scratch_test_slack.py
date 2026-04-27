"""Quick Slack connectivity test."""
import os, sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

from slack_notifier import SlackNotifier
slack = SlackNotifier()
print(f'Webhook URL: ...{slack.webhook_url[-20:]}')
print(f'Bot token type: {slack.bot_token[:10]}...')
print(f'User ID: {slack.user_id}')
print()

print('Testing webhook...')
slack.send_error_alert(
    customer_name='SYSTEM VALIDATION',
    activity_date='2026-04-13',
    activity='Slack Connectivity Test',
    vehicle_type='N/A',
    error_reason='If you see this, Slack notifications are working! This is a test.',
    tw_confirmation='VALIDATION-TEST',
)
print('\nDone.')
