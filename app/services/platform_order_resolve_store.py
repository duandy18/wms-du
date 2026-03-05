# app/services/platform_order_resolve_store.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_utils import norm_platform, norm_shop_id
from app.services.store_service import StoreService


async def resolve_store_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    store_name: Optional[str],
) -> int:
    plat = norm_platform(platform)
    sid = norm_shop_id(shop_id)

    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM stores
                     WHERE platform = :p
                       AND shop_id  = :s
                     LIMIT 1
                    """
                ),
                {"p": plat, "s": sid},
            )
        )
        .mappings()
        .first()
    )
    if row and row.get("id") is not None:
        return int(row["id"])

    await StoreService.ensure_store(
        session,
        platform=plat,
        shop_id=sid,
        name=store_name or f"{plat}-{sid}",
    )

    row2 = (
        (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM stores
                     WHERE platform = :p
                       AND shop_id  = :s
                     LIMIT 1
                    """
                ),
                {"p": plat, "s": sid},
            )
        )
        .mappings()
        .first()
    )
    if not row2 or row2.get("id") is None:
        raise RuntimeError(f"ensure_store failed: platform={plat} shop_id={sid}")
    return int(row2["id"])


async def load_shop_id_by_store_id(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
) -> Optional[str]:
    """
    用 store_id 反查平台 shop_id（绑定表唯一域是 platform+shop_id+merchant_code）。
    """
    plat = norm_platform(platform)
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT shop_id
                      FROM stores
                     WHERE id = :sid
                       AND platform = :p
                     LIMIT 1
                    """
                ),
                {"sid": int(store_id), "p": plat},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    v = row.get("shop_id")
    return norm_shop_id(str(v)) if v is not None else None
