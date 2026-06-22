import logging
from typing import Optional, Dict, Any, List

import httpx

from .config import WaplexConfig

logger = logging.getLogger("waplex")


class WAPlexError(Exception):
    """Raised when the WAPlex gateway returns an error or is unreachable."""


class WAPlexClient:
    """
    Async client for the Evolution-based WhatsApp platform.

    Auth scopes:
      * Admin endpoints (tenant provisioning) use X-Admin-Key.
      * Per-tenant endpoints (sessions) use that tenant's X-Tenant-Key.
    """

    def __init__(self, config: WaplexConfig):
        self.cfg = config

    def _admin_headers(self) -> Dict[str, str]:
        return {"X-Admin-Key": self.cfg.admin_key, "Content-Type": "application/json"}

    def _tenant_headers(self, api_key: str) -> Dict[str, str]:
        return {"X-Tenant-Key": api_key, "Content-Type": "application/json"}

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.cfg.base}{path}"
        async with httpx.AsyncClient(timeout=self.cfg.timeout) as client:
            try:
                resp = await client.request(method, url, **kwargs)
            except httpx.HTTPError as e:
                logger.error("WAPlex connection error %s %s: %s", method, url, e)
                raise WAPlexError(f"WAPlex gateway unreachable: {e}")

        if resp.status_code >= 400:
            logger.error("WAPlex %s %s %s: %s", resp.status_code, method, url, resp.text)
            raise WAPlexError(f"WAPlex {resp.status_code}: {resp.text}")

        return resp.json() if resp.content else {}

    # --- Admin: tenant provisioning ---

    async def create_tenant(self, name: str, webhook_url: Optional[str] = None) -> Dict[str, Any]:
        return await self._request(
            "POST", "/tenants/",
            headers=self._admin_headers(),
            json={"name": name, "webhook_url": webhook_url},
        )

    async def update_tenant(self, tenant_id: str, *, webhook_url: Optional[str] = None,
                            name: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if webhook_url is not None:
            body["webhook_url"] = webhook_url
        if name is not None:
            body["name"] = name
        return await self._request(
            "PATCH", f"/tenants/{tenant_id}", headers=self._admin_headers(), json=body
        )

    async def find_tenant_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        tenants: List[Dict[str, Any]] = await self._request(
            "GET", "/tenants/", headers=self._admin_headers()
        )
        for t in tenants or []:
            if t.get("name") == name:
                return t
        return None

    # --- Tenant: session lifecycle ---

    async def start_session(self, api_key: str, number: Optional[str] = None) -> Dict[str, Any]:
        # `number` is a query param (the link-with-phone-number / pairing-code flow).
        params = {"number": number} if number else None
        return await self._request(
            "POST", "/sessions/start", headers=self._tenant_headers(api_key), params=params
        )

    async def get_qr(self, api_key: str) -> Dict[str, Any]:
        return await self._request("GET", "/sessions/qr", headers=self._tenant_headers(api_key))

    async def get_status(self, api_key: str) -> Dict[str, Any]:
        return await self._request("GET", "/sessions/status", headers=self._tenant_headers(api_key))

    async def stop_session(self, api_key: str) -> Dict[str, Any]:
        return await self._request("DELETE", "/sessions/stop", headers=self._tenant_headers(api_key))
