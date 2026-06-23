import logging
from dataclasses import dataclass
from typing import Optional

from .client import WAPlexClient, WAPlexError

logger = logging.getLogger("waplex")


@dataclass
class ProvisionResult:
    tenant_id: str   # the WAPlex tenant id (store as e.g. waplex_tenant_id)
    api_key: str     # the WAPlex X-Tenant-Key (store as e.g. waplex_api_key)


async def ensure_provisioned(
    client: WAPlexClient,
    *,
    name: str,
    webhook_url: str,
    existing_key: Optional[str] = None,
    existing_id: Optional[str] = None,
) -> ProvisionResult:
    """
    Idempotently ensure a WAPlex tenant exists and return its id + key.

    Pass the values you already have stored (existing_key/existing_id); if a key
    is present this is a no-op. Otherwise it creates the tenant, recovering by
    name on collision (HTTP 409). The CALLER is responsible for persisting the result.

    `name` should be a stable, unique identifier for the tenant (a slug works well).
    `webhook_url` is where wa-platform forwards inbound messages — typically
    WaplexConfig.inbound_url().

    Raises WAPlexError on network failures, auth errors, or a failed webhook repoint.
    """
    if existing_key:
        return ProvisionResult(tenant_id=existing_id or "", api_key=existing_key)

    try:
        record = await client.create_tenant(name=name, webhook_url=webhook_url)
    except WAPlexError as e:
        # Recover from name-collisions (either 409 Conflict or 400 Bad Request if it already exists)
        is_collision = (e.status_code == 409) or (e.status_code == 400 and "already exists" in str(e))
        if not is_collision:
            raise
        record = await client.find_tenant_by_name(name)
        if not record:
            raise WAPlexError(
                f"WAPlex tenant '{name}' not found after name collision (status {e.status_code})",
                status_code=e.status_code
            ) from e
        if webhook_url and record.get("webhook_url") != webhook_url:
            try:
                record = await client.update_tenant(str(record.get("id")), webhook_url=webhook_url)
                logger.info("WAPlex repointed webhook for '%s' -> %s", name, webhook_url)
            except WAPlexError as update_err:
                raise WAPlexError(
                    f"WAPlex tenant '{name}' exists but webhook repoint failed: {update_err}"
                ) from update_err

    api_key = record.get("api_key")
    if not api_key:
        raise WAPlexError(f"WAPlex tenant '{name}' response missing api_key field")

    result = ProvisionResult(tenant_id=str(record.get("id")), api_key=api_key)
    logger.info("WAPlex provisioned tenant '%s' -> %s", name, result.tenant_id)
    return result
