# app/api/routers/platform_orders_address_fact_repo.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _get(addr: Any, key: str) -> Any:
    if addr is None:
        return None
    if isinstance(addr, dict):
        return addr.get(key)
    return getattr(addr, key, None)


def _to_raw_dict(address: Any) -> Dict[str, Any]:
    if address is None:
        return {}
    if isinstance(address, dict):
        return dict(address)
    # 尝试把对象的常用字段拉平到 raw
    raw: Dict[str, Any] = {}
    for k in ["province", "city", "province_code", "city_code", "receiver_name", "receiver_phone", "detail", "address"]:
        v = _get(address, k)
        if v is not None:
            raw[k] = v
    return raw


async def upsert_platform_order_address(
    session: AsyncSession,
    *,
    scope: str,
    platform: str,
    store_id: int,
    ext_order_no: str,
    address: Any,
) -> None:
    raw = _to_raw_dict(address)
    province = _s(_get(address, "province"))
    city = _s(_get(address, "city"))
    province_code = _s(_get(address, "province_code"))
    city_code = _s(_get(address, "city_code"))

    await session.execute(
        text(
            """
            INSERT INTO platform_order_addresses(
              scope, platform, store_id, ext_order_no,
              province, city, province_code, city_code,
              raw, created_at, updated_at
            )
            VALUES(
              :scope, :platform, :store_id, :ext_order_no,
              :province, :city, :province_code, :city_code,
              CAST(:raw AS jsonb), now(), now()
            )
            ON CONFLICT (scope, platform, store_id, ext_order_no)
            DO UPDATE SET
              province      = EXCLUDED.province,
              city          = EXCLUDED.city,
              province_code = EXCLUDED.province_code,
              city_code     = EXCLUDED.city_code,
              raw           = EXCLUDED.raw,
              updated_at    = now()
            """
        ),
        {
            "scope": str(scope).strip().upper(),
            "platform": str(platform).strip().upper(),
            "store_id": int(store_id),
            "ext_order_no": str(ext_order_no),
            "province": province,
            "city": city,
            "province_code": province_code,
            "city_code": city_code,
            "raw": __import__("json").dumps(raw, ensure_ascii=False),
        },
    )


async def load_platform_order_address(
    session: AsyncSession,
    *,
    scope: str,
    platform: str,
    store_id: int,
    ext_order_no: str,
) -> Optional[Dict[str, Any]]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      scope, platform, store_id, ext_order_no,
                      province, city, province_code, city_code,
                      raw, created_at, updated_at
                    FROM platform_order_addresses
                    WHERE scope = :scope
                      AND platform = :platform
                      AND store_id = :store_id
                      AND ext_order_no = :ext_order_no
                    LIMIT 1
                    """
                ),
                {
                    "scope": str(scope).strip().upper(),
                    "platform": str(platform).strip().upper(),
                    "store_id": int(store_id),
                    "ext_order_no": str(ext_order_no),
                },
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def detect_unique_scope_for_ext(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    ext_order_no: str,
) -> Optional[str]:
    """
    某些 dev/replay 路径没有显式 scope 输入：
    - 若同一 (platform,store_id,ext_order_no) 只存在一个 scope，则返回它
    - 若不存在返回 None
    - 若存在多个 scope（理论上不应发生），上层应报错要求显式 scope
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT scope
                FROM platform_order_addresses
                WHERE platform = :platform
                  AND store_id = :store_id
                  AND ext_order_no = :ext_order_no
                ORDER BY scope
                """
            ),
            {"platform": str(platform).strip().upper(), "store_id": int(store_id), "ext_order_no": str(ext_order_no)},
        )
    ).all()

    scopes = [str(r[0]) for r in rows if r and r[0] is not None]
    if not scopes:
        return None
    if len(scopes) == 1:
        return scopes[0]
    return "__AMBIGUOUS__"
