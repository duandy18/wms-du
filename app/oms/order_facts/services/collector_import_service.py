from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.order_facts.contracts.platform_order_mirror import (
    PlatformOrderMirrorImportIn,
    PlatformOrderMirrorLineImportIn,
    PlatformOrderMirrorOut,
)
from app.oms.order_facts.services.collector_export_client import fetch_collector_export_order
from app.oms.order_facts.services.platform_order_mirror_service import upsert_platform_order_mirror


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _line_from_collector(line: dict[str, Any]) -> PlatformOrderMirrorLineImportIn:
    return PlatformOrderMirrorLineImportIn(
        collector_line_id=int(line["collector_line_id"]),
        collector_order_id=int(line["collector_order_id"]),
        platform_order_no=str(line["platform_order_no"]),
        merchant_sku=line.get("merchant_sku"),
        platform_item_id=line.get("platform_item_id"),
        platform_sku_id=line.get("platform_sku_id"),
        title=line.get("title"),
        quantity=line.get("quantity") or 0,
        unit_price=line.get("unit_price"),
        line_amount=line.get("line_amount"),
        platform_fields=_dict(line.get("platform_fields")),
        raw_item_payload=line.get("raw_item_payload"),
    )


def _payload_from_collector(data: dict[str, Any]) -> PlatformOrderMirrorImportIn:
    lines = [
        _line_from_collector(line)
        for line in _list(data.get("lines"))
        if isinstance(line, dict)
    ]

    return PlatformOrderMirrorImportIn(
        collector_order_id=int(data["collector_order_id"]),
        collector_store_id=int(data["collector_store_id"]),
        collector_store_code=str(data["collector_store_code"]),
        collector_store_name=str(data["collector_store_name"]),
        platform=str(data["platform"]).lower(),  # type: ignore[arg-type]
        platform_order_no=str(data["platform_order_no"]),
        platform_status=data.get("platform_status"),
        source_updated_at=data.get("source_updated_at"),
        pulled_at=data.get("pulled_at"),
        last_synced_at=data.get("last_synced_at") or data.get("collector_last_synced_at"),
        receiver=_dict(data.get("receiver")),
        amounts=_dict(data.get("amounts")),
        platform_fields=_dict(data.get("platform_fields")),
        raw_refs=_dict(data.get("raw_refs")),
        lines=lines,
    )


async def import_platform_order_mirror_from_collector(
    session: AsyncSession,
    *,
    platform: str,
    collector_order_id: int,
) -> PlatformOrderMirrorOut:
    plat = (platform or "").strip().lower()
    data = await fetch_collector_export_order(
        platform=plat,
        collector_order_id=int(collector_order_id),
    )

    payload = _payload_from_collector(data)
    if payload.platform != plat:
        raise ValueError(f"collector payload platform mismatch: path={plat} payload={payload.platform}")

    return await upsert_platform_order_mirror(
        session,
        platform=plat,
        payload=payload,
    )
