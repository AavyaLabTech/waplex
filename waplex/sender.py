import logging
from typing import Optional, Dict, Any, List

import httpx
import requests

from .config import WaplexConfig

logger = logging.getLogger("waplex")

_OK_STATUS = (200, 201, 202)

_DEFAULT_MIME = {
    "image": "image/jpeg",
    "video": "video/mp4",
    "audio": "audio/mpeg",
    "document": "application/octet-stream",
}


def _clean_number(number: str) -> str:
    return (number or "").replace("+", "").strip()


class WaplexSender:
    """
    Synchronous outbound senders (safe to call from sync code / Celery tasks).

    The per-tenant credential is the tenant's X-Tenant-Key (api_key). Sends are
    queued by wa-platform's paced dispatcher and return HTTP 202.

    For use from async code (FastAPI routes, async workers), use AsyncWaplexSender.
    """

    def __init__(self, config: WaplexConfig):
        self.cfg = config

    def _headers(self, api_key: str) -> Dict[str, str]:
        return {"X-Tenant-Key": api_key, "Content-Type": "application/json"}

    def _post(self, path: str, api_key: str, payload: Dict[str, Any],
              timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        url = f"{self.cfg.base}/sessions/{path}"
        t = self.cfg.timeout if timeout is None else timeout
        try:
            resp = requests.post(url, json=payload, headers=self._headers(api_key), timeout=t)
            if resp.status_code not in _OK_STATUS:
                logger.error("WAPlex %s error %s: %s", path, resp.status_code, resp.text)
                return None
            return resp.json() if resp.content else {"status": "queued"}
        except requests.exceptions.RequestException as e:
            logger.error("WAPlex %s request error: %s", path, e)
            return None
        except Exception as e:
            logger.error("WAPlex %s unexpected error: %s", path, e)
            return None

    def send_text(self, api_key: str, number: str, text: str) -> Optional[Dict[str, Any]]:
        if not api_key or not number:
            logger.warning("WAPlex send_text skipped — missing api_key or number")
            return None
        data = self._post("send-text", api_key, {"number": _clean_number(number), "text": text})
        if not data:
            return None
        return {"message_id": data.get("message_id"), "status": data.get("status", "queued"),
                "recipient": number}

    def send_media(
        self,
        api_key: str,
        number: str,
        media_url: str,
        media_type: str = "image",
        caption: Optional[str] = None,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if media_type not in _DEFAULT_MIME:
            logger.error("Invalid media type: %s", media_type)
            return None
        if not api_key or not number:
            return None
        payload: Dict[str, Any] = {
            "number": _clean_number(number),
            "media_type": media_type,
            "mime_type": mime_type or _DEFAULT_MIME[media_type],
            "media": media_url,  # must be an HTTPS URL or base64 (plain http is rejected)
        }
        if filename:
            payload["filename"] = filename
        if caption and media_type in ("image", "video", "document"):
            payload["caption"] = caption
        data = self._post("send-media", api_key, payload, timeout=max(self.cfg.timeout, 25.0))
        if not data:
            return None
        return {"message_id": data.get("message_id"), "status": data.get("status", "queued"),
                "recipient": number, "media_type": media_type}

    def send_list(
        self,
        api_key: str,
        number: str,
        header: str,
        body: str,
        sections: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        WAPlex/Baileys has no native interactive list — degrade to formatted text.
        sections: [{"title": "...", "rows": [{"id": "...", "title": "...", "description": "..."}]}]
        """
        lines = [f"*{header}*", body, ""]
        for section in sections or []:
            if section.get("title"):
                lines.append(f"*{section['title']}*")
            for row in section.get("rows", []):
                label = f"• {row.get('title', '')} ({row.get('id', '')})"
                if row.get("description"):
                    label += f" — {row['description']}"
                lines.append(label)
            lines.append("")
        return self.send_text(api_key, number, "\n".join(lines).strip())

    def send_template(self, api_key: str, number: str, name: str,
                      parameters: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """No native templates on WAPlex — send the name (+ params) as text."""
        text = name if not parameters else name + "\n" + "\n".join(str(p) for p in parameters)
        return self.send_text(api_key, number, text)


class AsyncWaplexSender:
    """
    Async outbound senders using httpx — safe to call from FastAPI routes and
    async workers without blocking the event loop.

    The per-tenant credential is the tenant's X-Tenant-Key (api_key).
    """

    def __init__(self, config: WaplexConfig):
        self.cfg = config

    def _headers(self, api_key: str) -> Dict[str, str]:
        return {"X-Tenant-Key": api_key, "Content-Type": "application/json"}

    async def _post(self, path: str, api_key: str, payload: Dict[str, Any],
                    timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        url = f"{self.cfg.base}/sessions/{path}"
        t = self.cfg.timeout if timeout is None else timeout
        try:
            async with httpx.AsyncClient(timeout=t) as client:
                resp = await client.post(url, json=payload, headers=self._headers(api_key))
            if resp.status_code not in _OK_STATUS:
                logger.error("WAPlex %s error %s: %s", path, resp.status_code, resp.text)
                return None
            return resp.json() if resp.content else {"status": "queued"}
        except httpx.HTTPError as e:
            logger.error("WAPlex %s request error: %s", path, e)
            return None

    async def send_text(self, api_key: str, number: str, text: str) -> Optional[Dict[str, Any]]:
        if not api_key or not number:
            logger.warning("WAPlex send_text skipped — missing api_key or number")
            return None
        data = await self._post("send-text", api_key, {"number": _clean_number(number), "text": text})
        if not data:
            return None
        return {"message_id": data.get("message_id"), "status": data.get("status", "queued"),
                "recipient": number}

    async def send_media(
        self,
        api_key: str,
        number: str,
        media_url: str,
        media_type: str = "image",
        caption: Optional[str] = None,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if media_type not in _DEFAULT_MIME:
            logger.error("Invalid media type: %s", media_type)
            return None
        if not api_key or not number:
            return None
        payload: Dict[str, Any] = {
            "number": _clean_number(number),
            "media_type": media_type,
            "mime_type": mime_type or _DEFAULT_MIME[media_type],
            "media": media_url,
        }
        if filename:
            payload["filename"] = filename
        if caption and media_type in ("image", "video", "document"):
            payload["caption"] = caption
        data = await self._post("send-media", api_key, payload, timeout=max(self.cfg.timeout, 25.0))
        if not data:
            return None
        return {"message_id": data.get("message_id"), "status": data.get("status", "queued"),
                "recipient": number, "media_type": media_type}

    async def send_list(
        self,
        api_key: str,
        number: str,
        header: str,
        body: str,
        sections: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """WAPlex/Baileys has no native interactive list — degrade to formatted text."""
        lines = [f"*{header}*", body, ""]
        for section in sections or []:
            if section.get("title"):
                lines.append(f"*{section['title']}*")
            for row in section.get("rows", []):
                label = f"• {row.get('title', '')} ({row.get('id', '')})"
                if row.get("description"):
                    label += f" — {row['description']}"
                lines.append(label)
            lines.append("")
        return await self.send_text(api_key, number, "\n".join(lines).strip())

    async def send_template(self, api_key: str, number: str, name: str,
                            parameters: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """No native templates on WAPlex — send the name (+ params) as text."""
        text = name if not parameters else name + "\n" + "\n".join(str(p) for p in parameters)
        return await self.send_text(api_key, number, text)
