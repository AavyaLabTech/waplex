"""
WAPlex integration — reusable client for the Evolution-based WhatsApp platform.

Drop-in package for FastAPI SaaS apps. App-agnostic: no ORM, no auth, no app
imports. Wire it to your app with a handful of glue endpoints (see README.md).

Exports:
    WaplexConfig        - connection settings (base_url, admin_key, app_base_url)
    WAPlexClient        - async client: provisioning + session lifecycle
    WAPlexError         - raised on gateway/transport errors (carries .status_code)
    WaplexSender        - sync senders (text/media/list/template) — for Celery etc.
    AsyncWaplexSender   - async senders (text/media/list/template) — for FastAPI routes
    ensure_provisioned  - idempotent tenant provisioning helper
    parse_inbound       - parse a forwarded Evolution event -> InboundMessage
    parse_connection_update - parse a connection.update event -> state string
    InboundMessage      - dataclass: mobile, text, push_name, raw
"""
from .config import WaplexConfig
from .client import WAPlexClient, WAPlexError
from .sender import WaplexSender, AsyncWaplexSender
from .provisioning import ensure_provisioned, ProvisionResult
from .inbound import parse_inbound, parse_connection_update, InboundMessage

__version__ = "0.1.0"

__all__ = [
    "WaplexConfig",
    "WAPlexClient",
    "WAPlexError",
    "WaplexSender",
    "AsyncWaplexSender",
    "ensure_provisioned",
    "ProvisionResult",
    "parse_inbound",
    "parse_connection_update",
    "InboundMessage",
]
