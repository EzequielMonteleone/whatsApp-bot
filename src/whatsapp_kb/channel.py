import hashlib
import hmac
import logging

import httpx

from whatsapp_kb.config import Settings
from whatsapp_kb.types import Inbound

logger = logging.getLogger("whatsapp_kb")


def safe_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).digest(),
        hashlib.sha256(right.encode()).digest(),
    )


def inbound_messages(payload: dict) -> list[Inbound]:
    found: list[Inbound] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "")
            for message in value.get("messages") or []:
                if message.get("group_id"):
                    continue
                sender = str(message.get("from") or "")
                message_id = str(message.get("id") or "")
                if not sender or not message_id:
                    continue
                kind = str(message.get("type") or "")
                text = ""
                if kind == "text":
                    text = str((message.get("text") or {}).get("body") or "")
                found.append(
                    Inbound(
                        sender=sender,
                        message_id=message_id,
                        phone_number_id=phone_number_id,
                        kind=kind,
                        text=text,
                    )
                )
    return found


class WhatsAppChannel:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=30)

    def challenge(self, mode: str, token: str, challenge: str) -> str | None:
        if not self.settings.verify_token:
            return None
        if mode == "subscribe" and safe_equal(token, self.settings.verify_token):
            return challenge
        return None

    def signature_ok(self, body: bytes, header: str | None) -> bool:
        if not header or not header.startswith("sha256=") or not self.settings.app_secret:
            return False
        expected = hmac.new(self.settings.app_secret.encode(), body, hashlib.sha256).hexdigest()
        return safe_equal(header.removeprefix("sha256="), expected)

    def send_text(self, to: str, body: str) -> None:
        url = (
            f"https://graph.facebook.com/{self.settings.graph_version}/"
            f"{self.settings.phone_number_id}/messages"
        )
        response = self.client.post(
            url,
            headers={"Authorization": f"Bearer {self.settings.whatsapp_token}"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"body": body},
            },
        )
        if response.status_code >= 400:
            logger.error("WhatsApp rechazó el envío: %s", response.status_code)
