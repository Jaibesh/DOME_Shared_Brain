"""
slack_notifier.py — Slack DM Integration for MPWR Payment Agent

Posts notifications for:
  - ✅ Successful payment settlements in MPOWR
  - 🚨 Urgent Alerts: "On Ride" without a deposit
  - ❌ Errors
"""

import os
import requests as http_requests
from datetime import datetime

class SlackNotifier:
    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        self.user_id = os.getenv("SLACK_USER_ID", "")
        self.enabled = bool(self.webhook_url or self.bot_token)

        if not self.enabled:
            print("[Slack] WARNING: No SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN in .env. Falling back to console.")

    def _get_dm_channel(self) -> str | None:
        if not self.bot_token or not self.user_id:
            return None

        try:
            resp = http_requests.post(
                "https://slack.com/api/conversations.open",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                json={"users": self.user_id},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                return data["channel"]["id"]
            else:
                print(f"[Slack] Failed to open DM channel: {data.get('error')}")
                return None
        except Exception as e:
            print(f"[Slack] Error opening DM channel: {e}")
            return None

    def send_payment_success(self, tw_confirmation: str, mpowr_id: str, amount: float):
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Payment Settled in MPOWR",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Amount:*\n${amount:.2f} (Cash)"},
                    {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                    {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
                ]
            },
            {"type": "divider"},
        ]
        text = f"✅ Payment Settled: ${amount:.2f} for TW {tw_confirmation} (MPOWR #{mpowr_id})"
        self._send_message(blocks, text)

    def send_deposit_alert(self, tw_confirmation: str, mpowr_id: str, vehicle_qty: int, required_auth: float):
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 URGENT: ON RIDE WITHOUT DEPOSIT",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Reservation is marked *On Ride* in MPOWR, but the required deposit authorization of *${required_auth:.2f}* ({vehicle_qty} vehicles) has NOT been collected."
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                    {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔗 <https://mpwr-hq.poladv.com/orders/{mpowr_id}|Fix in MPOWR>"
                }
            },
            {"type": "divider"},
        ]
        text = f"🚨 ON RIDE WITHOUT DEPOSIT: TW {tw_confirmation} (MPOWR #{mpowr_id}) missing ${required_auth:.2f} auth."
        self._send_message(blocks, text)

    def send_error_alert(self, task: str, tw_confirmation: str, mpowr_id: str, error_msg: str, screenshot_path: str = None):
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"❌ Error: {task}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                    {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Details:*\n```{error_msg}```"
                }
            },
            {"type": "divider"},
        ]
        text = f"❌ Error ({task}): TW {tw_confirmation} (MPOWR #{mpowr_id}) - {error_msg}"
        self._send_message(blocks, text, screenshot_path)

    def _send_message(self, blocks: list | None, text: str, screenshot_path: str | None = None):
        if self.bot_token and self.user_id:
            channel = self._get_dm_channel()
            if channel:
                self._post_via_bot(channel, blocks, text, screenshot_path)
                return

        if self.webhook_url:
            self._post_via_webhook(blocks, text)
            if screenshot_path:
                print(f"[Slack] Screenshot saved locally: {screenshot_path}")
            return

        print(f"[Slack DISABLED] {text}")
        if screenshot_path:
            print(f"[Slack DISABLED] Screenshot at: {screenshot_path}")

    def _post_via_bot(self, channel: str, blocks: list | None, text: str, screenshot_path: str | None = None):
        try:
            payload = {"channel": channel, "text": text}
            if blocks:
                payload["blocks"] = blocks

            resp = http_requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                json=payload,
                timeout=10,
            )
            if not resp.json().get("ok"):
                if self.webhook_url:
                    self._post_via_webhook(blocks, text)
                else:
                    print(f"[Slack CONSOLE FALLBACK] {text}")
                return

            if screenshot_path and os.path.exists(screenshot_path):
                self._upload_file(channel, screenshot_path, "Error Screenshot")

        except Exception as e:
            print(f"[Slack] Error posting via bot: {e}")
            if self.webhook_url:
                self._post_via_webhook(blocks, text)

    def _post_via_webhook(self, blocks: list | None, text: str):
        try:
            payload = {"text": text}
            if blocks:
                payload["blocks"] = blocks
            http_requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception as e:
            print(f"[Slack] Error posting via webhook: {e}")

    def _upload_file(self, channel: str, file_path: str, comment: str = ""):
        try:
            file_size = os.path.getsize(file_path)
            filename = os.path.basename(file_path)

            resp1 = http_requests.get(
                "https://slack.com/api/files.getUploadURLExternal",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                params={"filename": filename, "length": file_size},
                timeout=10,
            )
            data1 = resp1.json()
            if not data1.get("ok"): return
            upload_url, file_id = data1["upload_url"], data1["file_id"]

            with open(file_path, "rb") as f:
                http_requests.post(upload_url, data=f.read(), headers={"Content-Type": "application/octet-stream"}, timeout=15)

            http_requests.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={"Authorization": f"Bearer {self.bot_token}", "Content-Type": "application/json"},
                json={"files": [{"id": file_id, "title": comment}], "channel_id": channel, "initial_comment": comment},
                timeout=10,
            )
        except Exception as e:
            pass

    def send_message(self, text: str, screenshot_path: str | None = None):
        """
        Public convenience method for sending simple text messages to Slack.
        Used by main.py for startup/shutdown and error notifications.
        """
        self._send_message(None, text, screenshot_path)


slack = SlackNotifier()
