"""
slack_notifier.py — Slack DM Integration for MPOWR Creator Bot

Posts notifications for EVERY reservation outcome:
  - ✅ Success: customer name, activity, vehicle, MPOWR ID + pre-submit screenshot
  - ❌ Error: full error details + error screenshot
  - ⚠️ Duplicate: existing MPOWR ID found
  - 🧪 Dry Run: form filled but not submitted
  - 💰 Price Override: mismatch detected and adjusted (or failed)
  - 📊 Batch Summary: end-of-run totals

Uses Slack Incoming Webhook for text messages and Bot Token for file uploads.

Setup:
    1. SLACK_WEBHOOK_URL in .env — for posting messages
    2. SLACK_BOT_TOKEN in .env — for uploading screenshot files
    3. SLACK_USER_ID in .env — for DM targeting
"""

import os
import json
import requests as http_requests
from datetime import datetime


class SlackNotifier:
    """
    Posts alerts + screenshots to Slack for EVERY reservation the bot processes.
    Primary alerting channel for the MPOWR Creator Bot.
    Falls back to console logging if Slack is not configured.
    """

    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        self.user_id = os.getenv("SLACK_USER_ID", "")
        self.enabled = bool(self.webhook_url or self.bot_token)

        if not self.enabled:
            print("[Slack] WARNING: No SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN in .env. "
                  "Slack notifications disabled — falling back to console logs.")

    def _get_dm_channel(self) -> str | None:
        """Opens a DM channel with the configured user. Returns channel ID."""
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

    # -----------------------------------------------------------------------
    # Core Notification Methods — ALL Reservation Outcomes
    # -----------------------------------------------------------------------

    def send_reservation_success(
        self,
        customer_name: str,
        tw_confirmation: str,
        activity: str,
        vehicle_type: str,
        mpowr_conf_id: str,
        activity_date: str = "",
        activity_time: str = "",
        vehicle_qty: int = 1,
        target_price: float = 0.0,
        screenshot_path: str | None = None,
    ):
        """
        Sends a SUCCESS notification with full details + screenshot.
        Called for every successfully created reservation.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Reservation Created Successfully",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                    {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_conf_id}"},
                    {"type": "mrkdwn", "text": f"*Activity:*\n{activity}"},
                    {"type": "mrkdwn", "text": f"*Vehicle:*\n{vehicle_type} x{vehicle_qty}"},
                    {"type": "mrkdwn", "text": f"*Date / Time:*\n{activity_date} {activity_time}"},
                    {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                ]
            },
        ]

        if target_price > 0:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Target Price:* ${target_price:.2f}"
                }
            })

        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"🕐 {timestamp} | 🔗 <https://mpwr-hq.poladv.com/orders/{mpowr_conf_id}|View in MPOWR>"}
            ]
        })
        blocks.append({"type": "divider"})

        fallback_text = (
            f"✅ Reservation Created: {customer_name}\n"
            f"MPOWR #{mpowr_conf_id} | TW: {tw_confirmation}\n"
            f"Activity: {activity} | Vehicle: {vehicle_type} x{vehicle_qty}\n"
            f"Date: {activity_date} {activity_time}"
        )

        self._send_message(blocks, fallback_text, screenshot_path)

    def send_error_alert(
        self,
        customer_name: str,
        activity_date: str,
        activity: str,
        vehicle_type: str,
        error_reason: str,
        screenshot_path: str | None = None,
        tw_confirmation: str = "",
    ):
        """
        Posts a rich error alert to Slack DM with Block Kit formatting.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "❌ MPOWR Auto-Creation Failed",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                    {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                    {"type": "mrkdwn", "text": f"*Activity:*\n{activity}"},
                    {"type": "mrkdwn", "text": f"*Vehicle:*\n{vehicle_type}"},
                    {"type": "mrkdwn", "text": f"*Date:*\n{activity_date}"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error_reason}```"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔗 <https://mpwr-hq.poladv.com/orders/create|Create Manually in MPOWR>"
                }
            },
            {"type": "divider"},
        ]

        fallback_text = (
            f"❌ MPOWR Auto-Creation Failed\n"
            f"Customer: {customer_name} | TW: {tw_confirmation}\n"
            f"Activity: {activity} | Vehicle: {vehicle_type}\n"
            f"Date: {activity_date}\n"
            f"Error: {error_reason}"
        )

        self._send_message(blocks, fallback_text, screenshot_path)

    def send_duplicate_alert(
        self,
        customer_name: str,
        tw_confirmation: str,
        existing_mpowr_id: str,
        activity: str = "",
        activity_date: str = "",
    ):
        """
        Notifies that a duplicate reservation was detected and skipped.
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ Duplicate Detected — Skipped",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                    {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                    {"type": "mrkdwn", "text": f"*Existing MPOWR ID:*\n#{existing_mpowr_id}"},
                    {"type": "mrkdwn", "text": f"*Activity:*\n{activity}"},
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"🔗 <https://mpwr-hq.poladv.com/orders/{existing_mpowr_id}|View Existing Reservation>"}
                ]
            },
            {"type": "divider"},
        ]

        fallback_text = (
            f"⚠️ Duplicate: {customer_name} (TW: {tw_confirmation})\n"
            f"Already exists as MPOWR #{existing_mpowr_id}. Skipped."
        )

        self._send_message(blocks, fallback_text)

    def send_dry_run_alert(
        self,
        customer_name: str,
        tw_confirmation: str,
        activity: str,
        vehicle_type: str,
        activity_date: str = "",
        activity_time: str = "",
        screenshot_path: str | None = None,
    ):
        """
        Notifies about a DRY_RUN completion with form screenshot.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🧪 DRY RUN — Form Filled (Not Submitted)",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                    {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                    {"type": "mrkdwn", "text": f"*Activity:*\n{activity}"},
                    {"type": "mrkdwn", "text": f"*Vehicle:*\n{vehicle_type}"},
                    {"type": "mrkdwn", "text": f"*Date / Time:*\n{activity_date} {activity_time}"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"},
                ]
            },
            {"type": "divider"},
        ]

        fallback_text = (
            f"🧪 DRY RUN: {customer_name} | TW: {tw_confirmation}\n"
            f"Activity: {activity} | Vehicle: {vehicle_type}\n"
            f"Date: {activity_date} {activity_time}"
        )

        self._send_message(blocks, fallback_text, screenshot_path)

    def send_price_override_alert(
        self,
        customer_name: str,
        tw_confirmation: str,
        mpowr_price: float,
        tripworks_price: float,
        override_success: bool,
        mpowr_conf_id: str = "",
    ):
        """
        Notifies about a price discrepancy and override attempt.
        """
        status = "✅ Override Successful" if override_success else "❌ Override Failed — Manual Action Required"
        text = (
            f"💰 *Price Discrepancy Detected*\n"
            f"Customer: {customer_name} | TW: {tw_confirmation} | MPOWR: {mpowr_conf_id}\n"
            f"MPOWR Price: ${mpowr_price:.2f} | TripWorks Price: ${tripworks_price:.2f}\n"
            f"Difference: ${abs(mpowr_price - tripworks_price):.2f}\n"
            f"Status: {status}"
        )

        self._send_message(None, text)

    def send_success_summary(self, created_count: int, failed_count: int,
                              skipped_count: int = 0, duplicates_count: int = 0):
        """
        Posts a run summary to Slack.
        Called after each scheduled_creator_job() batch completes.
        """
        if created_count == 0 and failed_count == 0 and skipped_count == 0 and duplicates_count == 0:
            return  # Nothing happened, don't spam

        emoji = "✅" if failed_count == 0 else "⚠️"
        parts = []
        if created_count > 0:
            parts.append(f"✅ Created {created_count} reservation(s)")
        if failed_count > 0:
            parts.append(f"❌ {failed_count} failed (see alerts above)")
        if duplicates_count > 0:
            parts.append(f"⏭️ {duplicates_count} duplicates skipped")
        if skipped_count > 0:
            parts.append(f"🧪 {skipped_count} dry run(s)")

        timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        text = f"{emoji} *MPOWR Creator Run Complete* ({timestamp})\n" + "\n".join(parts)

        self._send_message(None, text)

    # -----------------------------------------------------------------------
    # Core Message Dispatch — Tries Bot Token → Webhook → Console
    # -----------------------------------------------------------------------

    def _send_message(self, blocks: list | None, text: str,
                       screenshot_path: str | None = None):
        """
        Sends a message via the best available channel.
        Priority: Bot Token DM → Incoming Webhook → Console fallback.
        """
        # Try DM via Bot Token first (supports file uploads)
        if self.bot_token and self.user_id:
            channel = self._get_dm_channel()
            if channel:
                self._post_via_bot(channel, blocks, text, screenshot_path)
                return

        # Fallback to webhook (no file upload support)
        if self.webhook_url:
            self._post_via_webhook(blocks, text)
            if screenshot_path:
                print(f"[Slack] Screenshot saved locally (webhook can't upload): {screenshot_path}")
            return

        # Fallback to console
        print(f"[Slack DISABLED] {text}")
        if screenshot_path:
            print(f"[Slack DISABLED] Screenshot at: {screenshot_path}")

    def _post_via_bot(self, channel: str, blocks: list | None, text: str,
                      screenshot_path: str | None = None):
        """Post message via Slack Bot API (supports file uploads)."""
        try:
            payload = {
                "channel": channel,
                "text": text,
            }
            if blocks:
                payload["blocks"] = blocks

            resp = http_requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if not data.get("ok"):
                print(f"[Slack] Bot message failed: {data.get('error')}. Trying webhook fallback...")
                # Fallback to webhook if bot token doesn't have the right scopes
                if self.webhook_url:
                    self._post_via_webhook(blocks, text)
                else:
                    print(f"[Slack CONSOLE FALLBACK] {text}")
                return

            print(f"[Slack] Notification sent via DM.")

            # Upload screenshot if available
            if screenshot_path and os.path.exists(screenshot_path):
                self._upload_file(channel, screenshot_path, "Pre-submit screenshot")

        except Exception as e:
            print(f"[Slack] Error posting via bot: {e}")
            # Fallback to webhook
            if self.webhook_url:
                self._post_via_webhook(blocks, text)

    def send_scraper_summary(self, reservations_checked: int, total_waivers_found: int, new_waivers_found: int, errors: list[str]):
        """Sends a summary report after a run of the MPOWR Waiver Scraper."""
        if not self.enabled:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        status_text = "✅ *MPOWR Scraper Run Complete*"
        if errors:
            status_text = "⚠️ *MPOWR Scraper Run Complete (With Errors)*"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 MPOWR Scraper Summary",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{status_text}\n*Time:* {timestamp}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Reservations Scraped:*\n{reservations_checked}"},
                    {"type": "mrkdwn", "text": f"*New Waivers Found:*\n+{new_waivers_found}"},
                    {"type": "mrkdwn", "text": f"*Total Signed Waivers Checked:*\n{total_waivers_found}"}
                ]
            }
        ]

        if errors:
            error_bullets = "\n".join([f"• {e}" for e in errors[:5]])
            if len(errors) > 5:
                error_bullets += f"\n_...and {len(errors) - 5} more._"
                
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Errors Encountered:*\n{error_bullets}"
                }
            })

        self._send_message(blocks, f"MPOWR Scraper Run Complete: {reservations_checked} scraped, +{new_waivers_found} new waivers.")

    def _post_via_webhook(self, blocks: list | None, text: str):
        """Post message via Slack Incoming Webhook (no file upload)."""
        try:
            payload = {"text": text}
            if blocks:
                payload["blocks"] = blocks

            resp = http_requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                print("[Slack] Notification sent via webhook.")
            else:
                print(f"[Slack] Webhook failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"[Slack] Error posting via webhook: {e}")

    def _upload_file(self, channel: str, file_path: str, comment: str = ""):
        """Upload a file (screenshot) to a Slack channel/DM."""
        try:
            with open(file_path, "rb") as f:
                resp = http_requests.post(
                    "https://slack.com/api/files.upload",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    data={
                        "channels": channel,
                        "initial_comment": f"📸 {comment}",
                        "filename": os.path.basename(file_path),
                    },
                    files={"file": f},
                    timeout=30,
                )
            data = resp.json()
            if data.get("ok"):
                print(f"[Slack] Screenshot uploaded: {os.path.basename(file_path)}")
            else:
                print(f"[Slack] File upload failed: {data.get('error')}")
        except Exception as e:
            print(f"[Slack] Error uploading file: {e}")
