# app/oms/services/order_trace_helper.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _extract_ext_order_no_from_ref(platform: str, store_code: str, ref: str) -> Optional[str]:
    """
    从 ORD:{PLAT}:{store_code}:{ext_order_no} 中解析 ext_order_no，用于 status / trace 查询。
    """
    plat = platform.upper()
    prefix = f"ORD:{plat}:{store_code}:"
    if not ref.startswith(prefix):
        return None
    parts = ref.split(":", 3)
    if len(parts) != 4:
        return None
    return parts[3]


async def get_trace_id_for_order_ref(
    session: AsyncSession,
    *,
    platform: str,
    store_code: str,
    ref: str,
) -> Optional[str]:
    plat = platform.upper()

    ext_order_no = _extract_ext_order_no_from_ref(plat, store_code, ref)
    if not ext_order_no:
        raise ValueError(
            f"cannot resolve order trace_id: invalid ref={ref!r}, "
            f"expected 'ORD:{plat}:{store_code}:{{ext_order_no}}'"
        )

    row = await session.execute(
        text(
            """
            SELECT trace_id
              FROM orders
             WHERE platform = :p
               AND store_code  = :s
               AND ext_order_no = :o
             LIMIT 1
            """
        ),
        {"p": plat, "s": store_code, "o": ext_order_no},
    )
    rec = row.first()
    if rec and rec[0]:
        return str(rec[0])
    return None


async def set_order_status_by_ref(
    session: AsyncSession,
    *,
    platform: str,
    store_code: str,
    ref: str,
    new_status: str,
) -> None:
    """
    工具：根据 ref 更新 orders.status（用于 reserve/cancel/ship）。
    """
    plat = platform.upper()
    ext_order_no = _extract_ext_order_no_from_ref(plat, store_code, ref)
    if not ext_order_no:
        # 非订单驱动 ref，直接跳过
        return

    await session.execute(
        text(
            """
            UPDATE orders
               SET status = :st,
                   updated_at = NOW()
             WHERE platform = :p
               AND store_code  = :s
               AND ext_order_no = :o
            """
        ),
        {"st": new_status, "p": plat, "s": store_code, "o": ext_order_no},
    )
