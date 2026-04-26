# app/shipping_assist/shipment/repository_waybill_config.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .contracts_waybill_config import WaybillConfigOut


def _norm_required_text(raw: str, *, upper: bool = False) -> str:
    s = raw.strip()
    if not s:
        raise ValueError("required text is empty")
    return s.upper() if upper else s


def _norm_optional_text(raw: Optional[str], *, upper: bool = False) -> Optional[str]:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    return s.upper() if upper else s


def row_to_waybill_config(row: Any) -> WaybillConfigOut:
    return WaybillConfigOut(
        id=int(row["id"]),
        platform=row["platform"],
        store_code=row["store_code"],
        shipping_provider_id=int(row["shipping_provider_id"]),
        shipping_provider_name=row.get("shipping_provider_name"),
        customer_code=row["customer_code"],
        sender_name=row.get("sender_name"),
        sender_mobile=row.get("sender_mobile"),
        sender_phone=row.get("sender_phone"),
        sender_province=row.get("sender_province"),
        sender_city=row.get("sender_city"),
        sender_district=row.get("sender_district"),
        sender_address=row.get("sender_address"),
        active=bool(row.get("active", True)),
    )


async def list_waybill_configs(
    session: AsyncSession,
    *,
    active: Optional[bool] = None,
    platform: Optional[str] = None,
    store_code: Optional[str] = None,
    shipping_provider_id: Optional[int] = None,
    q: Optional[str] = None,
) -> List[WaybillConfigOut]:
    where: List[str] = []
    params: Dict[str, Any] = {}

    if active is not None:
        where.append("c.active = :active")
        params["active"] = active

    if platform:
        where.append("c.platform = :platform")
        params["platform"] = platform.strip().upper()

    if store_code:
        where.append("c.store_code = :store_code")
        params["store_code"] = store_code.strip()

    if shipping_provider_id is not None:
        where.append("c.shipping_provider_id = :shipping_provider_id")
        params["shipping_provider_id"] = int(shipping_provider_id)

    if q:
        where.append(
            """(
                c.platform ILIKE :q
                OR c.store_code ILIKE :q
                OR c.customer_code ILIKE :q
                OR c.sender_name ILIKE :q
                OR sp.name ILIKE :q
                OR sp.shipping_provider_code ILIKE :q
            )"""
        )
        params["q"] = f"%{q.strip()}%"

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sql = text(
        f"""
        SELECT
          c.id,
          c.platform,
          c.store_code,
          c.shipping_provider_id,
          sp.name AS shipping_provider_name,
          c.customer_code,
          c.sender_name,
          c.sender_mobile,
          c.sender_phone,
          c.sender_province,
          c.sender_city,
          c.sender_district,
          c.sender_address,
          c.active
        FROM electronic_waybill_configs c
        JOIN shipping_providers sp ON sp.id = c.shipping_provider_id
        {where_sql}
        ORDER BY c.platform ASC, c.store_code ASC, c.id ASC
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [row_to_waybill_config(r) for r in rows]


async def get_waybill_config(session: AsyncSession, config_id: int) -> Optional[WaybillConfigOut]:
    sql = text(
        """
        SELECT
          c.id,
          c.platform,
          c.store_code,
          c.shipping_provider_id,
          sp.name AS shipping_provider_name,
          c.customer_code,
          c.sender_name,
          c.sender_mobile,
          c.sender_phone,
          c.sender_province,
          c.sender_city,
          c.sender_district,
          c.sender_address,
          c.active
        FROM electronic_waybill_configs c
        JOIN shipping_providers sp ON sp.id = c.shipping_provider_id
        WHERE c.id = :config_id
        LIMIT 1
        """
    )
    row = (await session.execute(sql, {"config_id": int(config_id)})).mappings().first()
    return row_to_waybill_config(row) if row else None


async def get_active_waybill_config_for_shipment(
    session: AsyncSession,
    *,
    platform: str,
    store_code: str,
    shipping_provider_id: int,
) -> Optional[WaybillConfigOut]:
    sql = text(
        """
        SELECT
          c.id,
          c.platform,
          c.store_code,
          c.shipping_provider_id,
          sp.name AS shipping_provider_name,
          c.customer_code,
          c.sender_name,
          c.sender_mobile,
          c.sender_phone,
          c.sender_province,
          c.sender_city,
          c.sender_district,
          c.sender_address,
          c.active
        FROM electronic_waybill_configs c
        JOIN shipping_providers sp ON sp.id = c.shipping_provider_id
        WHERE c.platform = :platform
          AND c.store_code = :store_code
          AND c.shipping_provider_id = :shipping_provider_id
          AND c.active = true
        LIMIT 1
        """
    )
    row = (
        await session.execute(
            sql,
            {
                "platform": _norm_required_text(platform, upper=True),
                "store_code": _norm_required_text(store_code),
                "shipping_provider_id": int(shipping_provider_id),
            },
        )
    ).mappings().first()
    return row_to_waybill_config(row) if row else None


async def create_waybill_config(
    session: AsyncSession,
    *,
    platform: str,
    store_code: str,
    shipping_provider_id: int,
    customer_code: str,
    sender_name: Optional[str],
    sender_mobile: Optional[str],
    sender_phone: Optional[str],
    sender_province: Optional[str],
    sender_city: Optional[str],
    sender_district: Optional[str],
    sender_address: Optional[str],
    active: bool,
) -> WaybillConfigOut:
    sql = text(
        """
        INSERT INTO electronic_waybill_configs (
          platform,
          store_code,
          shipping_provider_id,
          customer_code,
          sender_name,
          sender_mobile,
          sender_phone,
          sender_province,
          sender_city,
          sender_district,
          sender_address,
          active
        )
        VALUES (
          :platform,
          :store_code,
          :shipping_provider_id,
          :customer_code,
          :sender_name,
          :sender_mobile,
          :sender_phone,
          :sender_province,
          :sender_city,
          :sender_district,
          :sender_address,
          :active
        )
        RETURNING id
        """
    )
    row = (
        await session.execute(
            sql,
            {
                "platform": _norm_required_text(platform, upper=True),
                "store_code": _norm_required_text(store_code),
                "shipping_provider_id": int(shipping_provider_id),
                "customer_code": _norm_required_text(customer_code),
                "sender_name": _norm_optional_text(sender_name),
                "sender_mobile": _norm_optional_text(sender_mobile),
                "sender_phone": _norm_optional_text(sender_phone),
                "sender_province": _norm_optional_text(sender_province),
                "sender_city": _norm_optional_text(sender_city),
                "sender_district": _norm_optional_text(sender_district),
                "sender_address": _norm_optional_text(sender_address),
                "active": bool(active),
            },
        )
    ).mappings().first()

    return await get_waybill_config(session, int(row["id"]))  # type: ignore[arg-type]


async def update_waybill_config(
    session: AsyncSession,
    *,
    config_id: int,
    platform: Optional[str] = None,
    store_code: Optional[str] = None,
    shipping_provider_id: Optional[int] = None,
    customer_code: Optional[str] = None,
    sender_name: Optional[str] = None,
    sender_mobile: Optional[str] = None,
    sender_phone: Optional[str] = None,
    sender_province: Optional[str] = None,
    sender_city: Optional[str] = None,
    sender_district: Optional[str] = None,
    sender_address: Optional[str] = None,
    active: Optional[bool] = None,
) -> Optional[WaybillConfigOut]:
    fields: Dict[str, Any] = {}

    if platform is not None:
        fields["platform"] = _norm_required_text(platform, upper=True)
    if store_code is not None:
        fields["store_code"] = _norm_required_text(store_code)
    if shipping_provider_id is not None:
        fields["shipping_provider_id"] = int(shipping_provider_id)
    if customer_code is not None:
        fields["customer_code"] = _norm_required_text(customer_code)

    if sender_name is not None:
        fields["sender_name"] = _norm_optional_text(sender_name)
    if sender_mobile is not None:
        fields["sender_mobile"] = _norm_optional_text(sender_mobile)
    if sender_phone is not None:
        fields["sender_phone"] = _norm_optional_text(sender_phone)
    if sender_province is not None:
        fields["sender_province"] = _norm_optional_text(sender_province)
    if sender_city is not None:
        fields["sender_city"] = _norm_optional_text(sender_city)
    if sender_district is not None:
        fields["sender_district"] = _norm_optional_text(sender_district)
    if sender_address is not None:
        fields["sender_address"] = _norm_optional_text(sender_address)
    if active is not None:
        fields["active"] = bool(active)

    if not fields:
        return await get_waybill_config(session, config_id)

    set_sql: List[str] = []
    params: Dict[str, Any] = {"config_id": int(config_id)}
    for idx, (key, value) in enumerate(fields.items()):
        pname = f"v{idx}"
        set_sql.append(f"{key} = :{pname}")
        params[pname] = value

    sql = text(
        f"""
        UPDATE electronic_waybill_configs
        SET {", ".join(set_sql)},
            updated_at = now()
        WHERE id = :config_id
        RETURNING id
        """
    )
    row = (await session.execute(sql, params)).mappings().first()
    if not row:
        return None

    return await get_waybill_config(session, int(row["id"]))
