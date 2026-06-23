from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class InboundMessage:
    """A normalized inbound WhatsApp message parsed from an Evolution event."""
    mobile: str           # sender number, no @-suffix, no '+'
    text: str             # message body / caption / interactive selection id
    push_name: str        # WhatsApp display name (may be "")
    raw: Dict[str, Any]   # the original forwarded payload


def _extract_text(message: Dict[str, Any]) -> str:
    if not message:
        return ""
    if "conversation" in message:
        return message["conversation"] or ""
    if "extendedTextMessage" in message:
        return message["extendedTextMessage"].get("text", "")
    for media in ("imageMessage", "videoMessage", "documentMessage"):
        if media in message:
            return message[media].get("caption", "")
    if "listResponseMessage" in message:
        sel = message["listResponseMessage"].get("singleSelectReply", {})
        return sel.get("selectedRowId", "") or message["listResponseMessage"].get("title", "")
    if "buttonsResponseMessage" in message:
        return message["buttonsResponseMessage"].get("selectedButtonId", "")
    return ""


def parse_inbound(payload: Dict[str, Any]) -> Optional[InboundMessage]:
    """
    Parse a forwarded Evolution webhook into an InboundMessage.

    Returns None for anything that should NOT trigger a bot reply: non-message
    events, messages we sent (fromMe), group chats, or empty/non-text content.
    """
    if not payload or payload.get("event") != "messages.upsert":
        return None

    data = payload.get("data") or {}
    if not data:
        return None

    key = data.get("key") or {}
    if key.get("fromMe"):
        return None

    remote_jid = key.get("remoteJid") or ""
    if not remote_jid or remote_jid.endswith("@g.us"):
        return None

    mobile = remote_jid.split("@")[0]
    text = _extract_text(data.get("message") or {}).strip()
    if not mobile or not text:
        return None

    return InboundMessage(
        mobile=mobile,
        text=text,
        push_name=data.get("pushName") or "",
        raw=payload,
    )


def parse_connection_update(payload: Dict[str, Any]) -> Optional[str]:
    """
    Parse a connection.update event into a normalized status string:
    "CONNECTED" | "CONNECTING" | "DISCONNECTED", or None if not a connection event.
    """
    if not payload or payload.get("event") != "connection.update":
        return None
    state = (payload.get("data") or {}).get("state")
    if not state:
        return None
    if state == "open":
        return "CONNECTED"
    if state == "connecting":
        return "CONNECTING"
    return "DISCONNECTED"
