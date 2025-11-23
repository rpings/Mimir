# -*- coding: utf-8 -*-
"""DingTalk notification client for Phase 3."""

import json
import os
from typing import Any

import httpx

from src.processors.base_processor import ProcessedEntry
from src.utils.logger import get_logger


class DingTalkNotifier:
    """Sends notifications to DingTalk webhook."""

    def __init__(
        self,
        webhook_url: str | None = None,
        secret: str | None = None,
    ):
        """Initialize DingTalk notifier.

        Args:
            webhook_url: DingTalk webhook URL. If None, reads from DINGTALK_WEBHOOK_URL env var.
            secret: DingTalk webhook secret for signature. If None, reads from DINGTALK_SECRET env var.
        """
        self.webhook_url = webhook_url or os.environ.get("DINGTALK_WEBHOOK_URL")
        self.secret = secret or os.environ.get("DINGTALK_SECRET")
        self.logger = get_logger(__name__)

        if not self.webhook_url:
            self.logger.warning("DingTalk webhook URL not configured. Notifications will be disabled.")

    def send_notification(
        self,
        entry: ProcessedEntry,
        message_type: str = "info",
    ) -> bool:
        """Send notification to DingTalk.

        Args:
            entry: ProcessedEntry to notify about.
            message_type: Type of message ('info', 'warning', 'error').

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.webhook_url:
            self.logger.debug("DingTalk webhook not configured, skipping notification")
            return False

        try:
            # Build message content
            title = entry.title[:100]  # Limit title length
            topics = ", ".join(entry.topics[:5])  # Limit topics
            priority_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(entry.priority, "⚪")

            message = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"{priority_emoji} {title}",
                    "text": f"""## {priority_emoji} {title}

**来源**: {entry.source_name or 'Unknown'}

**类型**: {entry.source_type or 'Unknown'}

**主题**: {topics or 'None'}

**优先级**: {entry.priority}

**链接**: [{str(entry.link)[:50]}...]({entry.link})

**摘要**: {entry.summary[:200] if entry.summary else 'No summary'}...
""",
                },
            }

            # Add signature if secret is provided
            if self.secret:
                import hmac
                import hashlib
                import base64
                import time
                import urllib.parse

                timestamp = str(round(time.time() * 1000))
                secret_enc = self.secret.encode("utf-8")
                string_to_sign = f"{timestamp}\n{self.secret}"
                string_to_sign_enc = string_to_sign.encode("utf-8")
                hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

                # Append signature to webhook URL
                webhook_url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
            else:
                webhook_url = self.webhook_url

            # Send notification
            with httpx.Client(timeout=10.0) as client:
                response = client.post(webhook_url, json=message)
                response.raise_for_status()

            self.logger.info(f"Sent DingTalk notification for: {title[:50]}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send DingTalk notification: {e}")
            return False

    async def send_notification_async(
        self,
        entry: ProcessedEntry,
        message_type: str = "info",
    ) -> bool:
        """Send notification to DingTalk asynchronously.

        Args:
            entry: ProcessedEntry to notify about.
            message_type: Type of message ('info', 'warning', 'error').

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.webhook_url:
            self.logger.debug("DingTalk webhook not configured, skipping notification")
            return False

        try:
            # Build message content (same as sync version)
            title = entry.title[:100]
            topics = ", ".join(entry.topics[:5])
            priority_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(entry.priority, "⚪")

            message = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"{priority_emoji} {title}",
                    "text": f"""## {priority_emoji} {title}

**来源**: {entry.source_name or 'Unknown'}

**类型**: {entry.source_type or 'Unknown'}

**主题**: {topics or 'None'}

**优先级**: {entry.priority}

**链接**: [{str(entry.link)[:50]}...]({entry.link})

**摘要**: {entry.summary[:200] if entry.summary else 'No summary'}...
""",
                },
            }

            # Add signature if secret is provided
            if self.secret:
                import hmac
                import hashlib
                import base64
                import time
                import urllib.parse

                timestamp = str(round(time.time() * 1000))
                secret_enc = self.secret.encode("utf-8")
                string_to_sign = f"{timestamp}\n{self.secret}"
                string_to_sign_enc = string_to_sign.encode("utf-8")
                hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

                webhook_url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
            else:
                webhook_url = self.webhook_url

            # Send notification asynchronously
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=message)
                response.raise_for_status()

            self.logger.info(f"Sent DingTalk notification for: {title[:50]}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send DingTalk notification: {e}")
            return False

