from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.oms.order_facts.contracts.fulfillment_conversion import (
    FulfillmentOrderConversionOut,
)
from app.oms.services.platform_order_ingest_flow import PlatformOrderIngestFlow


_PLATFORM_TABLES = {
    "pdd": ("oms_pdd_order_mirrors", "oms_pdd_order_mirror_lines"),
    "taobao": ("oms_taobao_order_mirrors", "oms_taobao_order_mirror_lines"),
    "jd": ("oms_jd_order_mirrors", "oms_jd_order_mirror_lines"),
}


class FulfillmentConversionNotFound(Exception):
    pass


class FulfillmentConversionValidationError(Exception):
    pass


def _tables(platform: str) -> tuple[str, str]:
    key = (platform or "").strip().lower()
    if key not in _PLATFORM_TABLES:
        raise FulfillmentConversionValidationError(f"unsupported platform: {platform!r}")
    return _PLATFORM_TABLES[key]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _as_positive_integral_decimal(value: Any, *, label: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FulfillmentConversionValidationError(f"{label} 非法：{value!r}") from exc

    if d <= 0:
        raise FulfillmentConversionValidationError(f"{label} 必须大于 0：{value!r}")

    if d != d.to_integral_value():
        raise FulfillmentConversionValidationError(f"{label} 必须为整数：{value!r}")

    return d


def _address_from_receiver(receiver: Mapping[str, Any]) -> dict[str, str]:
    name = _str_or_none(receiver.get("receiver_name")) or _str_or_none(receiver.get("name"))
    phone = (
        _str_or_none(receiver.get("receiver_phone"))
        or _str_or_none(receiver.get("phone"))
        or _str_or_none(receiver.get("mobile"))
    )
    province = (
        _str_or_none(receiver.get("province"))
        or _str_or_none(receiver.get("state"))
        or _str_or_none(receiver.get("receiver_state"))
    )
    city = _str_or_none(receiver.get("city"))
    district = (
        _str_or_none(receiver.get("district"))
        or _str_or_none(receiver.get("county"))
    )
    detail = (
        _str_or_none(receiver.get("detail"))
        or _str_or_none(receiver.get("address"))
        or _str_or_none(receiver.get("receiver_address"))
    )
    zipcode = _str_or_none(receiver.get("zipcode")) or _str_or_none(receiver.get("zip"))

    out = {
        "receiver_name": name,
        "receiver_phone": phone,
        "province": province,
        "city": city,
        "district": district,
        "detail": detail,
        "zipcode": zipcode,
    }
    return {k: v for k, v in out.items() if v is not None}


async def _load_header(
    session: AsyncSession,
    *,
    platform: str,
    mirror_id: int,
) -> dict[str, Any]:
    mirror_table, _line_table = _tables(platform)

    row = (
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
                  source_updated_at,
                  receiver_json,
                  amounts_json,
                  platform_fields_json,
                  raw_refs_json
                FROM {mirror_table}
                WHERE id = :mirror_id
                LIMIT 1
                """
            ),
            {"mirror_id": int(mirror_id)},
        )
    ).mappings().first()

    if row is None:
        raise FulfillmentConversionNotFound(f"{platform} platform order mirror not found: {int(mirror_id)}")

    data = dict(row)
    if data.get("wms_store_id") is None:
        raise FulfillmentConversionValidationError(
            f"平台订单镜像未匹配 WMS 店铺：platform={platform} mirror_id={int(mirror_id)}"
        )

    return data


async def _load_line_component_rows(
    session: AsyncSession,
    *,
    platform: str,
    mirror_id: int,
) -> list[dict[str, Any]]:
    _mirror_table, line_table = _tables(platform)

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  l.id AS line_id,
                  l.collector_line_id,
                  l.collector_order_id,
                  l.platform_order_no,
                  l.merchant_sku,
                  l.platform_item_id,
                  l.platform_sku_id,
                  l.title,
                  l.quantity AS line_quantity,
                  l.line_amount,

                  b.id AS binding_id,
                  b.fsku_id,

                  f.code AS fsku_code,
                  f.name AS fsku_name,
                  f.status AS fsku_status,

                  c.id AS component_id,
                  c.item_id AS component_item_id,
                  c.qty AS component_qty,
                  c.role AS component_role
                FROM {line_table} l
                LEFT JOIN merchant_code_fsku_bindings b
                  ON b.platform = :platform
                 AND b.store_code = (
                   SELECT m.collector_store_code
                   FROM {_tables(platform)[0]} m
                   WHERE m.id = l.mirror_id
                   LIMIT 1
                 )
                 AND b.merchant_code = l.merchant_sku
                LEFT JOIN fskus f
                  ON f.id = b.fsku_id
                LEFT JOIN fsku_components c
                  ON c.fsku_id = f.id
                WHERE l.mirror_id = :mirror_id
                ORDER BY l.id ASC, c.id ASC
                """
            ),
            {"platform": platform, "mirror_id": int(mirror_id)},
        )
    ).mappings().all()

    return [dict(row) for row in rows]


def _build_item_qty_map(rows: list[dict[str, Any]]) -> tuple[dict[int, int], list[dict[str, Any]], int]:
    if not rows:
        raise FulfillmentConversionValidationError("平台订单镜像没有订单行，不能转化为履约订单")

    item_qty_map: dict[int, int] = {}
    resolved: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_lines: set[int] = set()

    for row in rows:
        line_id = int(row["line_id"])

        merchant_code = _str_or_none(row.get("merchant_sku"))
        if not merchant_code:
            if line_id not in seen_lines:
                errors.append(f"line_id={line_id} 缺少 merchant_code")
                seen_lines.add(line_id)
            continue

        binding_id = row.get("binding_id")
        if binding_id is None:
            if line_id not in seen_lines:
                errors.append(f"line_id={line_id} merchant_code={merchant_code} 未绑定 FSKU")
                seen_lines.add(line_id)
            continue

        fsku_status = _str_or_none(row.get("fsku_status"))
        if fsku_status != "published":
            if line_id not in seen_lines:
                errors.append(f"line_id={line_id} merchant_code={merchant_code} 绑定的 FSKU 不是 published")
                seen_lines.add(line_id)
            continue

        component_item_id = row.get("component_item_id")
        component_qty = row.get("component_qty")
        if component_item_id is None or component_qty is None:
            if line_id not in seen_lines:
                errors.append(f"line_id={line_id} merchant_code={merchant_code} 对应 FSKU 没有 components")
                seen_lines.add(line_id)
            continue

        line_qty = _as_positive_integral_decimal(row.get("line_quantity"), label=f"line_id={line_id}.quantity")
        component_qty_dec = _as_positive_integral_decimal(
            component_qty,
            label=f"line_id={line_id}.component_qty",
        )
        final_qty_dec = line_qty * component_qty_dec

        if final_qty_dec != final_qty_dec.to_integral_value():
            errors.append(f"line_id={line_id} 展开后数量不是整数：{final_qty_dec}")
            continue

        item_id = int(component_item_id)
        final_qty = int(final_qty_dec)
        item_qty_map[item_id] = int(item_qty_map.get(item_id, 0)) + final_qty

        resolved.append(
            {
                "line_id": line_id,
                "collector_line_id": int(row["collector_line_id"]),
                "merchant_code": merchant_code,
                "fsku_id": int(row["fsku_id"]),
                "fsku_code": row.get("fsku_code"),
                "component_item_id": item_id,
                "qty": final_qty,
                "title": row.get("title"),
            }
        )

    if errors:
        raise FulfillmentConversionValidationError("；".join(errors[:10]))

    if not item_qty_map:
        raise FulfillmentConversionValidationError("没有可转化的商品行")

    lines_count = len({int(row["line_id"]) for row in rows})
    return item_qty_map, resolved, lines_count


async def convert_platform_order_mirror_to_fulfillment_order(
    session: AsyncSession,
    *,
    platform: str,
    mirror_id: int,
) -> FulfillmentOrderConversionOut:
    plat = (platform or "").strip().lower()
    header = await _load_header(session, platform=plat, mirror_id=int(mirror_id))
    rows = await _load_line_component_rows(session, platform=plat, mirror_id=int(mirror_id))

    item_qty_map, resolved, lines_count = _build_item_qty_map(rows)

    store_id = int(header["wms_store_id"])
    store_code = str(header["collector_store_code"])
    ext_order_no = str(header["platform_order_no"])

    receiver = _dict(header.get("receiver_json"))
    address = _address_from_receiver(receiver)
    buyer_name = address.get("receiver_name")
    buyer_phone = address.get("receiver_phone")

    trace = new_trace(f"oms:{plat}:fulfillment-order-conversion")

    items_payload = await PlatformOrderIngestFlow.build_items_payload_from_item_qty_map(
        session,
        store_id=store_id,
        item_qty_map=item_qty_map,
        source="oms/fulfillment-order-conversion",
        extras={
            "platform_order_mirror_id": int(mirror_id),
            "collector_order_id": int(header["collector_order_id"]),
            "platform_order_no": ext_order_no,
        },
    )

    try:
        out = await PlatformOrderIngestFlow.run_tail_from_items_payload(
            session,
            platform=plat,
            store_code=store_code,
            store_id=store_id,
            ext_order_no=ext_order_no,
            occurred_at=None,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            address=address or None,
            items_payload=items_payload,
            trace_id=trace.trace_id,
            source="oms/fulfillment-order-conversion",
            extras={
                "platform_order_mirror_id": int(mirror_id),
                "collector_order_id": int(header["collector_order_id"]),
                "platform_order_no": ext_order_no,
            },
            resolved=resolved,
            unresolved=[],
            facts_written=0,
            allow_manual_continue=False,
            risk_flags=[],
            risk_level=None,
            risk_reason=None,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return FulfillmentOrderConversionOut(
        ok=True,
        platform=plat,
        mirror_id=int(mirror_id),
        order_id=int(out["id"]) if out.get("id") is not None else None,
        ref=str(out.get("ref") or f"ORD:{plat}:{store_code}:{ext_order_no}"),
        status=str(out.get("status") or "OK"),
        store_id=store_id,
        store_code=store_code,
        ext_order_no=ext_order_no,
        lines_count=lines_count,
        item_lines_count=len(item_qty_map),
        fulfillment_status=out.get("fulfillment_status"),
        blocked_reasons=out.get("blocked_reasons"),
        risk_flags=[str(x) for x in out.get("risk_flags") or []],
    )
