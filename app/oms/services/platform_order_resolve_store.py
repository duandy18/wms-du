# app/oms/services/platform_order_resolve_store.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.services.platform_order_resolve_utils import norm_platform, norm_store_code
from app.oms.services.store_service import StoreService


async def resolve_store_id(
    session: AsyncSession,
    *,
    platform: str,
    store_code: str,
    store_name: Optional[str],
) -> int:
    plat = norm_platform(platform)
    sid = norm_store_code(store_code)

    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM stores
                     WHERE platform = :p
                       AND store_code  = :s
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
        store_code=sid,
        store_name=store_name or f"{plat}-{sid}",
    )

    row2 = (
        (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM stores
                     WHERE platform = :p
                       AND store_code  = :s
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
        raise RuntimeError(f"ensure_store failed: platform={plat} store_code={sid}")
    return int(row2["id"])


async def load_store_code_by_store_id(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
) -> Optional[str]:
    """
    用 store_id 反查平台 store_code（绑定表唯一域是 platform+store_code+merchant_code）。
    """
    plat = norm_platform(platform)
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT store_code
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
    v = row.get("store_code")
    return norm_store_code(str(v)) if v is not None else None
