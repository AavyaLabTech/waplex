from dataclasses import dataclass


@dataclass
class WaplexConfig:
    """
    Connection settings for the WAPlex (Evolution wa-platform) gateway.

    base_url:     wa-platform API root incl. /api/v1, e.g.
                  "https://wa.example.com:8030/api/v1"
    admin_key:    X-Admin-Key for tenant provisioning. MUST equal the
                  wa-platform's ADMIN_API_KEY env var.
    app_base_url: public base URL of THIS SaaS app, used to build the inbound
                  webhook URL wa-platform forwards messages to, e.g.
                  "https://app.mybiz.com"
    inbound_path: path of your inbound receiver (mount it at this path).
    timeout:      default HTTP timeout (seconds).
    """
    base_url: str
    admin_key: str
    app_base_url: str
    inbound_path: str = "/whatsapp/waplex/inbound"
    timeout: float = 20.0

    @property
    def base(self) -> str:
        return self.base_url.rstrip("/")

    def inbound_url(self) -> str:
        return f"{self.app_base_url.rstrip('/')}{self.inbound_path}"
