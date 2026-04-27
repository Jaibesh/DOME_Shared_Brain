"""
slack_notifier.py — Unified Slack Notification System for All DOME Agents

Merges the richest Block Kit formatting from all 3 agent versions into one
canonical module. Every agent gets the same rich notification capabilities.

Notification types:
  - Reservation: success, error, duplicate, dry run, price override, batch summary
  - Update/Cancel: update success, cancel success, minor update
  - Payment: payment settled, deposit alert
  - Generic: send_message, agent startup/shutdown

Setup (per-agent .env):
    SLACK_WEBHOOK_URL=https://hooks.slack.com/...
    SLACK_BOT_TOKEN=xoxb-...
    SLACK_USER_ID=U...

Usage:
    from shared.slack_notifier import SlackNotifier
    slack = SlackNotifier(agent_name="mpwr_creator")
    slack.send_reservation_success(customer_name="John", ...)
"""

import os
import requests as http_requests
from datetime import datetime


class SlackNotifier:
    """
    Unified Slack notification system for all DOME agents.
    Falls back to console logging if Slack is not configured.
    """

    def __init__(self, agent_name: str = "dome_agent"):
        self.agent_name = agent_name
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        self.user_id = os.getenv("SLACK_USER_ID", "")
        self.channel = os.getenv("SLACK_CHANNEL", "").lstrip("#")  # Slack API needs bare name or ID, not #name
        
        # Optional routing for Payment Settlements specifically
        self.payment_bot_token = os.getenv("SLACK_PAYMENT_BOT_TOKEN", "")
        self.payment_channel = os.getenv("SLACK_PAYMENT_CHANNEL", "").lstrip("#")
        
        self.enabled = bool(self.webhook_url or self.bot_token or self.payment_bot_token)

        if not self.enabled:
            print(f"[Slack:{agent_name}] WARNING: No SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN. "
                  "Notifications disabled — falling back to console.")

    def _get_dm_channel(self, override_token: str = None) -> str | None:
        """Opens a DM channel with the configured user."""
        token = override_token or self.bot_token
        if not token or not self.user_id:
            return None
        try:
            resp = http_requests.post(
                "https://slack.com/api/conversations.open",
                headers={"Authorization": f"Bearer {token}"},
                json={"users": self.user_id},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                return data["channel"]["id"]
            print(f"[Slack:{self.agent_name}] DM channel failed: {data.get('error')}")
            return None
        except Exception as e:
            print(f"[Slack:{self.agent_name}] Error opening DM: {e}")
            return None

    # ── Context footer (appended to every notification) ───────────────────
    def _agent_context(self) -> dict:
        """Returns a Block Kit context element identifying the agent + timestamp."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"🤖 `{self.agent_name}` | 🕐 {ts}"}
            ]
        }

    # ═══════════════════════════════════════════════════════════════════════
    # RESERVATION NOTIFICATIONS (from Creator Agent)
    # ═══════════════════════════════════════════════════════════════════════

    def send_reservation_success(self, customer_name: str, tw_confirmation: str,
                                  activity: str, vehicle_type: str, mpowr_conf_id: str,
                                  activity_date: str = "", activity_time: str = "",
                                  vehicle_qty: int = 1, target_price: float = 0.0,
                                  screenshot_path: str | None = None):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "✅ Reservation Created Successfully", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_conf_id}"},
                {"type": "mrkdwn", "text": f"*Activity:*\n{activity}"},
                {"type": "mrkdwn", "text": f"*Vehicle:*\n{vehicle_type} x{vehicle_qty}"},
                {"type": "mrkdwn", "text": f"*Date / Time:*\n{activity_date} {activity_time}"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
            ]},
        ]
        if target_price > 0:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Target Price:* ${target_price:.2f}"}})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Reservation Link:*\n<https://mpwr-hq.poladv.com/orders/{mpowr_conf_id}|View in MPOWR>"}})
        blocks.append(self._agent_context())
        blocks.append({"type": "divider"})

        fallback = (f"✅ Reservation Created: {customer_name}\n"
                    f"MPOWR #{mpowr_conf_id} | TW: {tw_confirmation}\n"
                    f"Activity: {activity} | Vehicle: {vehicle_type} x{vehicle_qty}\n"
                    f"Date: {activity_date} {activity_time}")
        self._send_message(blocks, fallback, screenshot_path)

    def send_error_alert(self, customer_name: str = "", activity_date: str = "",
                         activity: str = "", vehicle_type: str = "",
                         error_reason: str = "", screenshot_path: str | None = None,
                         tw_confirmation: str = "", mpowr_id: str = "", task: str = ""):
        """Unified error alert — works for all agent types."""
        title = f"❌ Error: {task}" if task else "❌ MPOWR Auto-Operation Failed"
        fields = []
        if customer_name: fields.append({"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"})
        if tw_confirmation: fields.append({"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"})
        if mpowr_id: fields.append({"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"})
        if activity: fields.append({"type": "mrkdwn", "text": f"*Activity:*\n{activity}"})
        if vehicle_type: fields.append({"type": "mrkdwn", "text": f"*Vehicle:*\n{vehicle_type}"})
        if activity_date: fields.append({"type": "mrkdwn", "text": f"*Date:*\n{activity_date}"})

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}},
        ]
        if fields:
            blocks.append({"type": "section", "fields": fields})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Error:*\n```{error_reason}```"}})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "🔗 <https://mpwr-hq.poladv.com/orders/create|Create Manually in MPOWR>"}})
        blocks.append(self._agent_context())
        blocks.append({"type": "divider"})

        fallback = f"❌ Error: {customer_name or 'N/A'} | TW: {tw_confirmation} | {error_reason}"
        self._send_message(blocks, fallback, screenshot_path)

    def send_duplicate_alert(self, customer_name: str, tw_confirmation: str,
                              existing_mpowr_id: str, activity: str = "", activity_date: str = ""):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "⚠️ Duplicate Detected — Skipped", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*Existing MPOWR ID:*\n#{existing_mpowr_id}"},
                {"type": "mrkdwn", "text": f"*Activity:*\n{activity}"},
            ]},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"<https://mpwr-hq.poladv.com/orders/{existing_mpowr_id}|View in MPOWR>"}},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"⚠️ Duplicate: {customer_name} (TW: {tw_confirmation}) → MPOWR #{existing_mpowr_id}"
        self._send_message(blocks, fallback)

    def send_minor_update_alert(self, customer_name: str, tw_confirmation: str,
                                 mpowr_id: str, waivers_complete: int, waivers_expected: int):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "📝 Minor Update / Waiver Signed", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"TripWorks sent an update for `{tw_confirmation}` (MPOWR `#{mpowr_id}`), but core details haven't changed.\n*MPOWR reschedule skipped.*"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*Waivers Signed:*\n{waivers_complete} / {waivers_expected}"},
            ]},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"📝 Minor Update: {customer_name} ({tw_confirmation}) — Waivers: {waivers_complete}/{waivers_expected}"
        self._send_message(blocks, fallback)

    def send_dry_run_alert(self, customer_name: str, tw_confirmation: str,
                            activity: str, vehicle_type: str,
                            activity_date: str = "", activity_time: str = "",
                            screenshot_path: str | None = None):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "🧪 DRY RUN — Form Filled (Not Submitted)", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*Activity:*\n{activity}"},
                {"type": "mrkdwn", "text": f"*Vehicle:*\n{vehicle_type}"},
                {"type": "mrkdwn", "text": f"*Date / Time:*\n{activity_date} {activity_time}"},
            ]},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"🧪 DRY RUN: {customer_name} | {activity} | {vehicle_type}"
        self._send_message(blocks, fallback, screenshot_path)

    def send_price_override_alert(self, customer_name: str, tw_confirmation: str,
                                   mpowr_price: float, tripworks_price: float,
                                   override_success: bool, mpowr_conf_id: str = ""):
        status = "✅ Override Successful" if override_success else "❌ Override Failed — Manual Action Required"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "💰 Price Discrepancy Detected", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*MPOWR Price:*\n${mpowr_price:.2f}"},
                {"type": "mrkdwn", "text": f"*TripWorks Price:*\n${tripworks_price:.2f}"},
                {"type": "mrkdwn", "text": f"*Difference:*\n${abs(mpowr_price - tripworks_price):.2f}"},
                {"type": "mrkdwn", "text": f"*Status:*\n{status}"},
            ]},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"💰 Price Override: {customer_name} | MPOWR ${mpowr_price:.2f} vs TW ${tripworks_price:.2f} | {status}"
        self._send_message(blocks, fallback)

    def send_success_summary(self, created_count: int = 0, failed_count: int = 0,
                              skipped_count: int = 0, duplicates_count: int = 0,
                              updated_count: int = 0, cancelled_count: int = 0):
        if all(c == 0 for c in [created_count, failed_count, skipped_count, duplicates_count, updated_count, cancelled_count]):
            return
        emoji = "✅" if failed_count == 0 else "⚠️"
        parts = []
        if created_count > 0: parts.append(f"✅ Created {created_count}")
        if updated_count > 0: parts.append(f"🔄 Updated {updated_count}")
        if cancelled_count > 0: parts.append(f"🗑️ Cancelled {cancelled_count}")
        if failed_count > 0: parts.append(f"❌ {failed_count} failed")
        if duplicates_count > 0: parts.append(f"⏭️ {duplicates_count} duplicates")
        if skipped_count > 0: parts.append(f"🧪 {skipped_count} dry runs")
        ts = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        text = f"{emoji} *{self.agent_name} Run Complete* ({ts})\n" + "\n".join(parts)
        self._send_message(None, text)

    # ═══════════════════════════════════════════════════════════════════════
    # UPDATE / CANCEL NOTIFICATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def send_update_success(self, customer_name: str, tw_confirmation: str,
                             mpowr_id: str, changes: str = "", screenshot_path: str | None = None):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "🔄 Reservation Updated in MPOWR", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
            ]},
        ]
        if changes:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Changes:*\n{changes}"}})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"<https://mpwr-hq.poladv.com/orders/{mpowr_id}|View in MPOWR>"}})
        blocks.append(self._agent_context())
        blocks.append({"type": "divider"})
        fallback = f"🔄 Updated: {customer_name} ({tw_confirmation}) → MPOWR #{mpowr_id}"
        self._send_message(blocks, fallback, screenshot_path)

    def send_cancel_success(self, customer_name: str, tw_confirmation: str, mpowr_id: str):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "🗑️ Reservation Cancelled in MPOWR", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
            ]},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"🗑️ Cancelled: {customer_name} ({tw_confirmation}) — MPOWR #{mpowr_id}"
        self._send_message(blocks, fallback)

    # ═══════════════════════════════════════════════════════════════════════
    # PAYMENT NOTIFICATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def send_payment_success(self, tw_confirmation: str, mpowr_id: str, amount: float):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "✅ Payment Settled in MPOWR", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Amount:*\n${amount:.2f} (Cash)"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
            ]},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"✅ Payment: ${amount:.2f} for TW {tw_confirmation} (MPOWR #{mpowr_id})"
        self._send_message(blocks, fallback, 
                           override_token=self.payment_bot_token,
                           override_channel=self.payment_channel)

    def send_deposit_alert(self, tw_confirmation: str, mpowr_id: str,
                            vehicle_qty: int, required_auth: float):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "🚨 URGENT: ON RIDE WITHOUT DEPOSIT", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"Reservation is *On Ride* but deposit of *${required_auth:.2f}* ({vehicle_qty} vehicles) NOT collected."}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
            ]},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"<https://mpwr-hq.poladv.com/orders/{mpowr_id}|Fix in MPOWR>"}},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"🚨 ON RIDE WITHOUT DEPOSIT: TW {tw_confirmation} (MPOWR #{mpowr_id}) missing ${required_auth:.2f}"
        self._send_message(blocks, fallback)

    def send_overdue_rental_alert(self, tw_confirmation: str, customer_name: str, 
                                  mpowr_id: str, minutes_late: int, return_time: str):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "⚠️ OVERDUE RENTAL", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"Vehicle for *{customer_name}* is *{minutes_late} minutes* past its return time ({return_time}).\nStatus is still 'Rental Out'."}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*TW Conf:*\n{tw_confirmation}"},
                {"type": "mrkdwn", "text": f"*MPOWR ID:*\n#{mpowr_id}"},
            ]},
            self._agent_context(),
            {"type": "divider"},
        ]
        fallback = f"⚠️ OVERDUE RENTAL: {customer_name} ({tw_confirmation}) is {minutes_late} mins late (due at {return_time})."
        self._send_message(blocks, fallback)

    # ═══════════════════════════════════════════════════════════════════════
    # GENERIC / CONVENIENCE
    # ═══════════════════════════════════════════════════════════════════════

    def send_message(self, text: str, screenshot_path: str | None = None):
        """Public convenience method for simple text messages."""
        self._send_message(None, text, screenshot_path)

    # ═══════════════════════════════════════════════════════════════════════
    # CORE MESSAGE DISPATCH — Bot Token → Webhook → Console
    # ═══════════════════════════════════════════════════════════════════════

    def _send_message(self, blocks: list | None, text: str,
                       screenshot_path: str | None = None,
                       override_token: str = None, override_channel: str = None):
        
        token = override_token or self.bot_token
        if token:
            # For override routing, if override_channel is blank, fall back to DM
            if override_token and override_channel:
                channel = override_channel
            elif override_token and not override_channel:
                channel = self._get_dm_channel(override_token)
            else:
                channel = self.channel or self._get_dm_channel()
                
            if channel:
                self._post_via_bot(channel, blocks, text, screenshot_path, token)
                return
                
        if self.webhook_url:
            self._post_via_webhook(blocks, text)
            if screenshot_path:
                print(f"[Slack:{self.agent_name}] Screenshot saved locally: {screenshot_path}")
            return
            
        print(f"[Slack DISABLED:{self.agent_name}] {text}")

    def _post_via_bot(self, channel: str, blocks: list | None, text: str,
                      screenshot_path: str | None = None,
                      override_token: str = None):
        token = override_token or self.bot_token
        try:
            payload = {"channel": channel, "text": text}
            if blocks:
                payload["blocks"] = blocks
            resp = http_requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json=payload, timeout=10,
            )
            data = resp.json()
            if not data.get("ok"):
                print(f"[Slack:{self.agent_name}] Bot failed: {data.get('error')}. Trying webhook...")
                if self.webhook_url:
                    self._post_via_webhook(blocks, text)
                else:
                    print(f"[Slack CONSOLE:{self.agent_name}] {text}")
                return
            print(f"[Slack:{self.agent_name}] DM sent.")
            if screenshot_path and os.path.exists(screenshot_path):
                self._upload_file(channel, screenshot_path, "Screenshot", token)
        except Exception as e:
            print(f"[Slack:{self.agent_name}] Error: {e}")
            if self.webhook_url:
                self._post_via_webhook(blocks, text)

    def _post_via_webhook(self, blocks: list | None, text: str):
        try:
            payload = {"text": text}
            if blocks:
                payload["blocks"] = blocks
            resp = http_requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code != 200:
                print(f"[Slack:{self.agent_name}] Webhook failed: {resp.status_code}")
        except Exception as e:
            print(f"[Slack:{self.agent_name}] Webhook error: {e}")

    def _upload_file(self, channel: str, file_path: str, comment: str = "", override_token: str = None):
        """Upload via modern 3-step Slack file upload flow (Nov 2025+)."""
        token = override_token or self.bot_token
        try:
            file_size = os.path.getsize(file_path)
            filename = os.path.basename(file_path)
            # Step 1: Get upload URL
            r1 = http_requests.get(
                "https://slack.com/api/files.getUploadURLExternal",
                headers={"Authorization": f"Bearer {token}"},
                params={"filename": filename, "length": file_size}, timeout=10)
            d1 = r1.json()
            if not d1.get("ok"): return
            # Step 2: Upload bytes
            with open(file_path, "rb") as f:
                http_requests.post(d1["upload_url"], data=f.read(),
                    headers={"Content-Type": "application/octet-stream"}, timeout=15)
            # Step 3: Finalize
            http_requests.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"files": [{"id": d1["file_id"], "title": f"📸 {comment}"}],
                      "channel_id": channel, "initial_comment": f"📸 {comment}"}, timeout=10)
            print(f"[Slack:{self.agent_name}] Screenshot uploaded: {filename}")
        except Exception as e:
            print(f"[Slack:{self.agent_name}] Upload error: {e}")
