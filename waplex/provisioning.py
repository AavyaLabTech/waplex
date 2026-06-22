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
    name on collision. The CALLER is responsible for persisting the result.

    `name` should be a stable, unique identifier for the tenant (a slug works well).
    `webhook_url` is where wa-platform forwards inbound messages — typically
    WaplexConfig.inbound_url().
    """
    if existing_key:
        return ProvisionResult(tenant_id=existing_id or "", api_key=existing_key)

    try:
        record = await client.create_tenant(name=name, webhook_url=webhook_url)
    except WAPlexError:
        # Most likely the name already exists — recover its api_key by listing, and
        # repoint its webhook_url if it drifted (e.g. registered with an old URL).
        record = await client.find_tenant_by_name(name)
        if not record:
            raise
        if webhook_url and record.get("webhook_url") != webhook_url:
            try:
                record = await client.update_tenant(str(record.get("id")), webhook_url=webhook_url)
                logger.info("WAPlex repointed webhook for '%s' -> %s", name, webhook_url)
            except WAPlexError as e:
                logger.warning("WAPlex webhook repoint failed for '%s': %s", name, e)

    result = ProvisionResult(tenant_id=str(record.get("id")), api_key=record.get("api_key"))
    logger.info("WAPlex provisioned tenant '%s' -> %s", name, result.tenant_id)
    return result
