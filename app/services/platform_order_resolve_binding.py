# app/services/platform_order_resolve_binding.py
from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_utils import norm_platform, norm_shop_id


async def resolve_fsku_id_by_binding(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    merchant_code: str,
) -> Tuple[Optional[int], Optional[str]]:
    """
    一码一对一：返回 (fsku_id, reason_if_not_ok)

    reason:
      - None: 命中 published FSKU
      - FSKU_NOT_PUBLISHED: 绑定存在但指向非 published
      - CODE_NOT_BOUND: 未找到绑定
    """
    plat = norm_platform(platform)
    sid = norm_shop_id(shop_id)
    code = (merchant_code or "").strip()
    if not code:
        return (None, "CODE_NOT_BOUND")

    # 1) 优先：绑定存在且 published
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT b.fsku_id
                      FROM merchant_code_fsku_bindings b
                      JOIN fskus f ON f.id = b.fsku_id
                     WHERE b.platform = :p
                       AND b.shop_id = :shop_id
                       AND b.merchant_code = :code
                       AND f.status = 'published'
                     LIMIT 1
                    """
                ),
                {"p": plat, "shop_id": sid, "code": code},
            )
        )
        .mappings()
        .first()
    )
    if row and row.get("fsku_id") is not None:
        return (int(row["fsku_id"]), None)

    # 2) 再查：绑定存在但非 published（给更精确原因）
    row2 = (
        (
            await session.execute(
                text(
                    """
                    SELECT b.fsku_id, f.status
                      FROM merchant_code_fsku_bindings b
                      LEFT JOIN fskus f ON f.id = b.fsku_id
                     WHERE b.platform = :p
                       AND b.shop_id = :shop_id
                       AND b.merchant_code = :code
                     LIMIT 1
                    """
                ),
                {"p": plat, "shop_id": sid, "code": code},
            )
        )
        .mappings()
        .first()
    )
    if row2 and row2.get("fsku_id") is not None:
        st = str(row2.get("status") or "")
        if st and st != "published":
            return (None, "FSKU_NOT_PUBLISHED")
        return (None, "CODE_NOT_BOUND")

    return (None, "CODE_NOT_BOUND")
