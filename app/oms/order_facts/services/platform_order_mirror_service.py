from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.order_facts.contracts.platform_order_mirror import (
    PlatformOrderMirrorImportIn,
    PlatformOrderMirrorLineOut,
    PlatformOrderMirrorOut,
)


_PLATFORM_TABLES = {
    "pdd": ("oms_pdd_order_mirrors", "oms_pdd_order_mirror_lines"),
    "taobao": ("oms_taobao_order_mirrors", "oms_taobao_order_mirror_lines"),
    "jd": ("oms_jd_order_mirrors", "oms_jd_order_mirror_lines"),
}


def _tables(platform: str) -> tuple[str, str]:
    key = (platform or "").strip().lower()
    if key not in _PLATFORM_TABLES:
        raise ValueError(f"unsupported platform: {platform!r}")
    return _PLATFORM_TABLES[key]


def _dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None

    try:
        normalized = text_value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _json(value: Any) -> str:
    if value is None:
        value = {}
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _fmt_dt(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _fmt_dec(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _row_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return dict(row)


async def _resolve_wms_store_id(
    session: AsyncSession,
    *,
    platform: str,
    collector_store_code: str,
) -> int | None:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM stores
                 WHERE lower(platform) = :platform
                   AND store_code = :store_code
                 LIMIT 1
                """
            ),
            {
                "platform": platform.lower(),
                "store_code": str(collector_store_code),
            },
        )
    ).mappings().first()

    if row is None or row.get("id") is None:
        return None
    return int(row["id"])


async def upsert_platform_order_mirror(
    session: AsyncSession,
    *,
    platform: str,
    payload: PlatformOrderMirrorImportIn,
) -> PlatformOrderMirrorOut:
    plat = platform.strip().lower()
    if payload.platform != plat:
        raise ValueError(f"payload platform mismatch: path={plat} payload={payload.platform}")

    header_table, line_table = _tables(plat)

    wms_store_id = await _resolve_wms_store_id(
        session,
        platform=plat,
        collector_store_code=payload.collector_store_code,
    )

    header = (
        await session.execute(
            text(
                f"""
                INSERT INTO {header_table} (
                  collector_order_id,
                  collector_store_id,
                  collector_store_code,
                  collector_store_name,
                  wms_store_id,
                  platform_order_no,
                  platform_status,
                  import_status,
                  mirror_status,
                  source_updated_at,
                  pulled_at,
                  collector_last_synced_at,
                  receiver_json,
                  amounts_json,
                  platform_fields_json,
                  raw_refs_json,
                  imported_at,
                  last_synced_at,
                  updated_at
                )
                VALUES (
                  :collector_order_id,
                  :collector_store_id,
                  :collector_store_code,
                  :collector_store_name,
                  :wms_store_id,
                  :platform_order_no,
                  :platform_status,
                  'imported',
                  'active',
                  :source_updated_at,
                  :pulled_at,
                  :collector_last_synced_at,
                  CAST(:receiver_json AS jsonb),
                  CAST(:amounts_json AS jsonb),
                  CAST(:platform_fields_json AS jsonb),
                  CAST(:raw_refs_json AS jsonb),
                  now(),
                  now(),
                  now()
                )
                ON CONFLICT (collector_order_id) DO UPDATE
                SET
                  collector_store_id = EXCLUDED.collector_store_id,
                  collector_store_code = EXCLUDED.collector_store_code,
                  collector_store_name = EXCLUDED.collector_store_name,
                  wms_store_id = EXCLUDED.wms_store_id,
                  platform_order_no = EXCLUDED.platform_order_no,
                  platform_status = EXCLUDED.platform_status,
                  import_status = 'imported',
                  mirror_status = 'active',
                  source_updated_at = EXCLUDED.source_updated_at,
                  pulled_at = EXCLUDED.pulled_at,
                  collector_last_synced_at = EXCLUDED.collector_last_synced_at,
                  receiver_json = EXCLUDED.receiver_json,
                  amounts_json = EXCLUDED.amounts_json,
                  platform_fields_json = EXCLUDED.platform_fields_json,
                  raw_refs_json = EXCLUDED.raw_refs_json,
                  last_synced_at = now(),
                  updated_at = now()
                RETURNING
                  id,
                  collector_order_id,
                  collector_store_id,
                  collector_store_code,
                  collector_store_name,
                  wms_store_id,
                  platform_order_no,
                  platform_status,
                  import_status,
                  mirror_status,
                  source_updated_at,
                  pulled_at,
                  collector_last_synced_at,
                  imported_at,
                  last_synced_at,
                  receiver_json,
                  amounts_json,
                  platform_fields_json,
                  raw_refs_json
                """
            ),
            {
                "collector_order_id": int(payload.collector_order_id),
                "collector_store_id": int(payload.collector_store_id),
                "collector_store_code": str(payload.collector_store_code),
                "collector_store_name": str(payload.collector_store_name),
                "wms_store_id": wms_store_id,
                "platform_order_no": str(payload.platform_order_no),
                "platform_status": payload.platform_status,
                "source_updated_at": _dt(payload.source_updated_at),
                "pulled_at": _dt(payload.pulled_at),
                "collector_last_synced_at": _dt(payload.last_synced_at),
                "receiver_json": _json(payload.receiver),
                "amounts_json": _json(payload.amounts),
                "platform_fields_json": _json(payload.platform_fields),
                "raw_refs_json": _json(payload.raw_refs),
            },
        )
    ).mappings().one()

    mirror_id = int(header["id"])

    await session.execute(
        text(f"DELETE FROM {line_table} WHERE mirror_id = :mirror_id"),
        {"mirror_id": mirror_id},
    )

    for line in payload.lines:
        await session.execute(
            text(
                f"""
                INSERT INTO {line_table} (
                  mirror_id,
                  collector_line_id,
                  collector_order_id,
                  platform_order_no,
                  merchant_sku,
                  platform_item_id,
                  platform_sku_id,
                  title,
                  quantity,
                  unit_price,
                  line_amount,
                  platform_fields_json,
                  raw_item_payload_json,
                  updated_at
                )
                VALUES (
                  :mirror_id,
                  :collector_line_id,
                  :collector_order_id,
                  :platform_order_no,
                  :merchant_sku,
                  :platform_item_id,
                  :platform_sku_id,
                  :title,
                  :quantity,
                  :unit_price,
                  :line_amount,
                  CAST(:platform_fields_json AS jsonb),
                  CAST(:raw_item_payload_json AS jsonb),
                  now()
                )
                """
            ),
            {
                "mirror_id": mirror_id,
                "collector_line_id": int(line.collector_line_id),
                "collector_order_id": int(line.collector_order_id),
                "platform_order_no": str(line.platform_order_no),
                "merchant_sku": line.merchant_sku,
                "platform_item_id": line.platform_item_id,
                "platform_sku_id": line.platform_sku_id,
                "title": line.title,
                "quantity": Decimal(line.quantity),
                "unit_price": line.unit_price,
                "line_amount": line.line_amount,
                "platform_fields_json": _json(line.platform_fields),
                "raw_item_payload_json": _json(line.raw_item_payload),
            },
        )

    await session.commit()

    out = await get_platform_order_mirror_detail(session, platform=plat, mirror_id=mirror_id)
    if out is None:
        raise RuntimeError(f"mirror not found after upsert: platform={plat} id={mirror_id}")
    return out


async def list_platform_order_mirrors(
    session: AsyncSession,
    *,
    platform: str,
    limit: int,
    offset: int,
) -> list[PlatformOrderMirrorOut]:
    header_table, _line_table = _tables(platform)

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  id,
                  collector_order_id,
                  collector_store_id,
                  collector_store_code,
                  collector_store_name,
                  wms_store_id,
                  platform_order_no,
                  platform_status,
                  import_status,
                  mirror_status,
                  source_updated_at,
                  pulled_at,
                  collector_last_synced_at,
                  imported_at,
                  last_synced_at,
                  receiver_json,
                  amounts_json,
                  platform_fields_json,
                  raw_refs_json
                FROM {header_table}
                ORDER BY last_synced_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": int(limit), "offset": int(offset)},
        )
    ).mappings().all()

    return [_mirror_out(platform=platform, row=_row_dict(row), lines=[]) for row in rows]


async def get_platform_order_mirror_detail(
    session: AsyncSession,
    *,
    platform: str,
    mirror_id: int,
) -> PlatformOrderMirrorOut | None:
    header_table, line_table = _tables(platform)

    header = (
        await session.execute(
            text(
                f"""
                SELECT
                  id,
                  collector_order_id,
                  collector_store_id,
                  collector_store_code,
                  collector_store_name,
                  wms_store_id,
                  platform_order_no,
                  platform_status,
                  import_status,
                  mirror_status,
                  source_updated_at,
                  pulled_at,
                  collector_last_synced_at,
                  imported_at,
                  last_synced_at,
                  receiver_json,
                  amounts_json,
                  platform_fields_json,
                  raw_refs_json
                FROM {header_table}
                WHERE id = :mirror_id
                LIMIT 1
                """
            ),
            {"mirror_id": int(mirror_id)},
        )
    ).mappings().first()

    if header is None:
        return None

    line_rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  id,
                  collector_line_id,
                  collector_order_id,
                  platform_order_no,
                  merchant_sku,
                  platform_item_id,
                  platform_sku_id,
                  title,
                  quantity,
                  unit_price,
                  line_amount,
                  platform_fields_json,
                  raw_item_payload_json
                FROM {line_table}
                WHERE mirror_id = :mirror_id
                ORDER BY id ASC
                """
            ),
            {"mirror_id": int(mirror_id)},
        )
    ).mappings().all()

    lines = [_line_out(_row_dict(line)) for line in line_rows]
    return _mirror_out(platform=platform, row=_row_dict(header), lines=lines)


def _mirror_out(
    *,
    platform: str,
    row: Mapping[str, Any],
    lines: list[PlatformOrderMirrorLineOut],
) -> PlatformOrderMirrorOut:
    return PlatformOrderMirrorOut(
        id=int(row["id"]),
        collector_order_id=int(row["collector_order_id"]),
        collector_store_id=int(row["collector_store_id"]),
        collector_store_code=str(row["collector_store_code"]),
        collector_store_name=str(row["collector_store_name"]),
        wms_store_id=int(row["wms_store_id"]) if row.get("wms_store_id") is not None else None,
        platform=platform,  # type: ignore[arg-type]
        platform_order_no=str(row["platform_order_no"]),
        platform_status=row.get("platform_status"),
        import_status=str(row["import_status"]),
        mirror_status=str(row["mirror_status"]),
        source_updated_at=_fmt_dt(row.get("source_updated_at")),
        pulled_at=_fmt_dt(row.get("pulled_at")),
        collector_last_synced_at=_fmt_dt(row.get("collector_last_synced_at")),
        imported_at=_fmt_dt(row.get("imported_at")),
        last_synced_at=_fmt_dt(row.get("last_synced_at")),
        receiver=row.get("receiver_json") or {},
        amounts=row.get("amounts_json") or {},
        platform_fields=row.get("platform_fields_json") or {},
        raw_refs=row.get("raw_refs_json") or {},
        lines=lines,
    )


def _line_out(row: Mapping[str, Any]) -> PlatformOrderMirrorLineOut:
    return PlatformOrderMirrorLineOut(
        id=int(row["id"]),
        collector_line_id=int(row["collector_line_id"]),
        collector_order_id=int(row["collector_order_id"]),
        platform_order_no=str(row["platform_order_no"]),
        merchant_sku=row.get("merchant_sku"),
        platform_item_id=row.get("platform_item_id"),
        platform_sku_id=row.get("platform_sku_id"),
        title=row.get("title"),
        quantity=str(row.get("quantity") or "0"),
        unit_price=_fmt_dec(row.get("unit_price")),
        line_amount=_fmt_dec(row.get("line_amount")),
        platform_fields=row.get("platform_fields_json") or {},
        raw_item_payload=row.get("raw_item_payload_json"),
    )
