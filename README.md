# waplex

Reusable WhatsApp gateway plugin for FastAPI SaaS apps, built on the [Evolution wa-platform](https://github.com/EvolutionAPI/evolution-api).

Provides:
- **`waplex/`** — Python package: async client, sync senders, inbound parser, provisioning helper
- **`ui/waplex-panel.js`** — Self-contained React component for session management (connect / disconnect / pairing code)

---

## Repository structure

```
waplex/
├── pyproject.toml
├── waplex/
│   ├── __init__.py          exports: WaplexConfig, WAPlexClient, WaplexSender,
│   │                                 ensure_provisioned, parse_inbound,
│   │                                 parse_connection_update, InboundMessage
│   ├── config.py            WaplexConfig dataclass
│   ├── client.py            WAPlexClient (async httpx) — provisioning + session lifecycle
│   ├── sender.py            WaplexSender (sync requests) — text / media / list / template
│   ├── inbound.py           parse_inbound, parse_connection_update, InboundMessage
│   └── provisioning.py      ensure_provisioned, ProvisionResult
└── ui/
    └── waplex-panel.js      window.WaplexPanel React component
```

---

## Requirements

| Dependency | Version |
|---|---|
| Python | ≥ 3.10 |
| httpx | ≥ 0.27 |
| requests | ≥ 2.31 |
| FastAPI | any (not a hard dependency) |
| React (UI only) | ≥ 17 via CDN |

---

## Python package installation

```bash
# Install directly from git (no PyPI needed)
pip install git+https://github.com/your-org/waplex.git@main

# Pin to a release tag for stability
pip install git+https://github.com/your-org/waplex.git@v0.1.0
```

Add to `requirements.txt`:
```
waplex @ git+https://github.com/your-org/waplex.git@v0.1.0
```

---

## Backend integration (FastAPI)

### 1. Environment variables

Add these to your `.env` file:

| Variable | Description | Example |
|---|---|---|
| `WAPLEX_BASE_URL` | WAPlex API root including `/api/v1` | `http://wa.example.com:8030/api/v1` |
| `WAPLEX_ADMIN_KEY` | X-Admin-Key matching wa-platform's `ADMIN_API_KEY` | `my_secret_admin_key` |
| `APP_BASE_URL` | Public base URL of your SaaS app — used to build the inbound webhook URL. **Must be publicly reachable in production.** | `https://app.mybiz.com` |

In your settings class:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    waplex_base_url: str = "http://wa.example.com:8030/api/v1"
    waplex_admin_key: str = ""
    app_base_url: str = "http://localhost:9000"

    class Config:
        env_file = ".env"
```

### 2. Runtime singletons

Create `integrations/waplex_runtime.py` — the only glue between the package and your app's settings:

```python
from waplex import WaplexConfig, WAPlexClient, WaplexSender
from app.core.config import settings

waplex_config = WaplexConfig(
    base_url=settings.waplex_base_url,
    admin_key=settings.waplex_admin_key,
    app_base_url=settings.app_base_url,
    # inbound_path="/whatsapp/waplex/inbound",  # default, change if needed
    # timeout=20.0,                              # default
)
waplex_client = WAPlexClient(waplex_config)
waplex_sender = WaplexSender(waplex_config)
```

### 3. Tenant model

Add two columns to your tenant table:

```python
# SQLAlchemy example
waplex_tenant_id = Column(String, nullable=True)   # WAPlex internal tenant id
waplex_api_key   = Column(String, nullable=True)   # X-Tenant-Key for all per-tenant calls
```

Also ensure the tenant has a `whatsapp_number` field (the phone number used to initiate sessions, with country code, e.g. `919876543210`).

### 4. Provisioning service

Create `services/waplex_service.py` — wires your `Tenant` row to WAPlex and persists the credentials:

```python
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from waplex import ensure_provisioned as _ensure_provisioned
from app.integrations.waplex_runtime import waplex_client, waplex_config
from app.models.tenant import Tenant

_NON_PUBLIC = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

def _assert_public_inbound_url():
    url = waplex_config.inbound_url()
    host = (urlparse(url).hostname or "").lower()
    if host in _NON_PUBLIC:
        raise RuntimeError(
            f"app_base_url is not publicly reachable ({url!r}). "
            "Set it to your public domain before provisioning."
        )
    return url

async def ensure_provisioned(db: Session, tenant: Tenant) -> str:
    """Idempotent: returns existing key, or provisions + persists on first use."""
    if tenant.waplex_api_key:
        return tenant.waplex_api_key

    _assert_public_inbound_url()

    result = await _ensure_provisioned(
        waplex_client,
        name=tenant.tenant_id,           # stable unique slug for this tenant
        webhook_url=waplex_config.inbound_url(),
        existing_key=tenant.waplex_api_key,
        existing_id=tenant.waplex_tenant_id,
    )
    tenant.waplex_tenant_id = result.tenant_id
    tenant.waplex_api_key   = result.api_key
    db.commit()
    return result.api_key
```

### 5. Session management routes

Create `api/whatsapp_session.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from waplex import WAPlexError
from app.integrations.waplex_runtime import waplex_client
from app.services.waplex_service import ensure_provisioned
from app.core.database import get_db
from app.api.auth import check_owner   # your owner-auth dependency

router = APIRouter(prefix="/api/whatsapp/session", tags=["WhatsApp Session"])

class StartSessionRequest(BaseModel):
    number: Optional[str] = None

@router.post("/start")
async def start_session(
    payload: Optional[StartSessionRequest] = None,
    user: dict = Depends(check_owner),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(db, user["tenant_id"])
    number = (payload.number if payload else None) or tenant.whatsapp_number
    if not number:
        raise HTTPException(400, "No WhatsApp number configured.")
    try:
        api_key = await ensure_provisioned(db, tenant)
        result  = await waplex_client.start_session(api_key, number=number)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except WAPlexError as e:
        raise HTTPException(502, str(e))
    return {"status": result.get("status"), "pairing_code": result.get("pairing_code"), "number": number}

@router.get("/qr")
async def get_qr(user: dict = Depends(check_owner), db: Session = Depends(get_db)):
    tenant = _get_tenant(db, user["tenant_id"])
    if not tenant.waplex_api_key:
        raise HTTPException(400, "Session not started. Call /start first.")
    try:
        return await waplex_client.get_qr(tenant.waplex_api_key)
    except WAPlexError as e:
        raise HTTPException(502, str(e))

@router.get("/status")
async def get_status(user: dict = Depends(check_owner), db: Session = Depends(get_db)):
    tenant = _get_tenant(db, user["tenant_id"])
    if not tenant.waplex_api_key:
        return {"status": "NOT_INITIALIZED", "connected": False}
    try:
        return await waplex_client.get_status(tenant.waplex_api_key)
    except WAPlexError as e:
        raise HTTPException(502, str(e))

@router.post("/disconnect")
async def disconnect_session(user: dict = Depends(check_owner), db: Session = Depends(get_db)):
    tenant = _get_tenant(db, user["tenant_id"])
    if not tenant.waplex_api_key:
        return {"status": "success", "message": "No active session."}
    try:
        await waplex_client.stop_session(tenant.waplex_api_key)
    except WAPlexError as e:
        raise HTTPException(502, str(e))
    return {"status": "success", "message": "WhatsApp session disconnected."}

def _get_tenant(db, tenant_id):
    from app.models.tenant import Tenant
    t = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not t:
        raise HTTPException(404, "Tenant not found")
    return t
```

Register the router in your app:

```python
from app.api.whatsapp_session import router as wa_session_router
app.include_router(wa_session_router)
```

### 6. Inbound webhook

Create `api/whatsapp_inbound.py` — receives forwarded messages from WAPlex:

```python
from fastapi import APIRouter, Depends, Request, Header
from sqlalchemy.orm import Session
from typing import Optional
from waplex import parse_inbound
from app.core.database import get_db
from app.models.tenant import Tenant

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Inbound"])

@router.post("/waplex/inbound")
async def waplex_inbound(
    request: Request,
    x_tenant_key: Optional[str] = Header(None, alias="X-Tenant-Key"),
    db: Session = Depends(get_db),
):
    """Always returns 200 — prevents WAPlex retry storms on transient errors."""
    payload = await request.json()

    tenant = None
    if x_tenant_key:
        tenant = db.query(Tenant).filter(Tenant.waplex_api_key == x_tenant_key).first()
    if not tenant:
        return {"status": "ignored"}

    msg = parse_inbound(payload)
    if msg is None:
        return {"status": "ignored"}

    # msg.mobile     — sender number (no '+', no '@' suffix)
    # msg.text       — message body / caption / button/list selection id
    # msg.push_name  — WhatsApp display name
    # msg.raw        — full original payload
    await your_bot_handler(db, tenant, msg)
    return {"status": "success"}
```

Register it:

```python
from app.api.whatsapp_inbound import router as wa_inbound_router
app.include_router(wa_inbound_router)
```

### 7. Sending messages

Import `WaplexSender` from your runtime singletons and call it from anywhere (including Celery tasks):

```python
from app.integrations.waplex_runtime import waplex_sender

# Text
waplex_sender.send_text(tenant.waplex_api_key, "919876543210", "Your order has shipped!")

# Image
waplex_sender.send_media(
    tenant.waplex_api_key,
    "919876543210",
    media_url="https://cdn.example.com/invoice.pdf",
    media_type="document",
    caption="Your invoice",
    mime_type="application/pdf",
    filename="invoice.pdf",
)
```

Available sender methods:

| Method | Description |
|---|---|
| `send_text(api_key, number, text)` | Plain text message |
| `send_media(api_key, number, media_url, media_type, caption, mime_type, filename)` | Image / video / audio / document |
| `send_list(api_key, number, header, body, sections)` | Interactive list (degrades to formatted text on WAPlex/Baileys) |
| `send_template(api_key, number, name, parameters)` | Template message (degrades to text on WAPlex) |

---

## WaplexConfig reference

| Field | Type | Default | Description |
|---|---|---|---|
| `base_url` | `str` | — | WAPlex API root including `/api/v1` |
| `admin_key` | `str` | — | X-Admin-Key for tenant provisioning |
| `app_base_url` | `str` | — | Public base URL of your SaaS app |
| `inbound_path` | `str` | `/whatsapp/waplex/inbound` | Path where you mounted the inbound webhook |
| `timeout` | `float` | `20.0` | Default HTTP timeout in seconds |

---

## Session status values

| Status | Meaning |
|---|---|
| `NOT_INITIALIZED` | Tenant not yet provisioned or session never started |
| `CONNECTING` | Session started, waiting for pairing code entry |
| `CONNECTED` | WhatsApp linked and active |
| `DISCONNECTED` | Previously connected session lost (phone offline / logged out) |

---

## UI panel integration

The `ui/waplex-panel.js` component works with **vanilla React via CDN** (no npm build required).

### HTML setup

```html
<!-- React + ReactDOM (already in your app, or add here) -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>

<!-- WaplexPanel component -->
<script src="/static/waplex-panel.js"></script>

<!-- Mount point -->
<div id="wa-panel"></div>
```

### Mount the panel

```html
<script>
  const apiGet  = (path) => axios.get(path);
  const apiPost = (path, body) => axios.post(path, body);

  ReactDOM.render(
    React.createElement(window.WaplexPanel, {
      apiGet,
      apiPost,
      whatsappNumber: "{{ tenant.whatsapp_number }}",  // from your template / JS state
      showToast: (msg, type) => myToast(msg, type),    // optional
      Icon: window.Shared?.Icon,                        // optional — lucide-react icon component
    }),
    document.getElementById('wa-panel')
  );
</script>
```

### WaplexPanel props

| Prop | Type | Required | Description |
|---|---|---|---|
| `apiGet(path)` | `Function → Promise` | Yes | Wraps GET requests; must include auth headers |
| `apiPost(path, body)` | `Function → Promise` | Yes | Wraps POST requests; must include auth headers |
| `whatsappNumber` | `string` | Yes | The tenant's configured WA number (with country code) shown in idle state |
| `showToast(msg, type)` | `Function` | No | Notification callback. `type` is `'success'` or `'error'`. Falls back to `console.log/error`. |
| `Icon` | `React component` | No | Icon renderer accepting `{ name, size }`. Falls back to emoji text labels. |

### CSS variables (optional)

The panel uses CSS variables with sensible fallbacks. Override in your stylesheet to match your theme:

```css
:root {
  --primary:      #0d9488;
  --bg-card:      #ffffff;
  --bg-main:      #f9fafb;
  --border:       #e5e7eb;
  --text:         #111827;
  --text-muted:   #6b7280;
  --text-secondary: #374151;
}
```

---

## Checklist for a new SaaS integration

- [ ] Add `waplex` to `requirements.txt`
- [ ] Set `WAPLEX_BASE_URL`, `WAPLEX_ADMIN_KEY`, `APP_BASE_URL` in `.env`
- [ ] Create `integrations/waplex_runtime.py` (singletons)
- [ ] Add `waplex_tenant_id` + `waplex_api_key` columns to tenant model + run migration
- [ ] Create `services/waplex_service.py` (provisioning)
- [ ] Mount session routes (`api/whatsapp_session.py`)
- [ ] Mount inbound webhook (`api/whatsapp_inbound.py`) at `/whatsapp/waplex/inbound`
- [ ] Copy `ui/waplex-panel.js` to your static directory (or serve from CDN)
- [ ] Mount `<WaplexPanel>` in your settings page
