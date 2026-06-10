"""
Telegram alert sender — pushes a confirmed-detection photo to a Telegram chat
via the Bot API `sendPhoto` endpoint over HTTPS.

The photo is sent from an in-memory JPEG buffer (no file is written to the Pi's
SD card) and the network call runs on a background daemon thread so it never
blocks the deterrent loop or the alarm. Any failure is caught and logged — a
dropped alert must never crash the deterrent.
"""

import logging
import threading

import requests

log = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: float = 10.0):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.enabled = bool(token and chat_id)
        if not self.enabled:
            log.warning(
                "Telegram alerts disabled — set TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID to enable detection photos."
            )

    def send_photo_async(self, jpeg_bytes: bytes, caption: str) -> None:
        """Fire-and-forget: send the photo on a daemon thread, return immediately."""
        if not self.enabled:
            return
        threading.Thread(
            target=self._send,
            args=(jpeg_bytes, caption),
            daemon=True,
        ).start()

    def _send(self, jpeg_bytes: bytes, caption: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        try:
            resp = requests.post(
                url,
                data={"chat_id": self.chat_id, "caption": caption},
                files={"photo": ("detection.jpg", jpeg_bytes, "image/jpeg")},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                log.warning(
                    "Telegram sendPhoto failed: HTTP %s — %s",
                    resp.status_code, resp.text[:200],
                )
            else:
                log.info("Telegram alert sent.")
        except Exception as exc:   # network errors must not crash the deterrent
            log.warning("Telegram alert error: %s", exc)
