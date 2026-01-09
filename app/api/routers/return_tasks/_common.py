# app/api/routers/return_tasks/_common.py
from __future__ import annotations

import json
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# ✅ 出库事实识别口径（退货回仓只读上下文 + 自动回原批次共用）
SHIP_OUT_REASONS = ("SHIPMENT", "OUTBOUND_SHIP")


def parse_ext_order_no(order_ref: str) -> Optional[str]:
    """
    约定：ORD:{PLAT}:{shop_id}:{ext_order_no}
    ext_order_no 内部不应包含冒号；若包含，则保守处理为 split(":",3) 后取最后段。
    """
    s = str(order_ref or "").strip()
    if not s.startswith("ORD:"):
        return None
    parts = s.split(":", 3)
    if len(parts) != 4:
        return None
    return parts[3] or None


def safe_meta_to_dict(meta_val) -> dict:
    if meta_val is None:
        return {}
    if isinstance(meta_val, dict):
        return meta_val
    if isinstance(meta_val, str):
        try:
            return json.loads(meta_val)
        except Exception:
            return {}
    return {}


async def calc_remaining_qty(
    session: AsyncSession,
    *,
    order_ref: str,
    warehouse_id: Optional[int] = None,
    days: int = 3650,
) -> Optional[int]:
    """
    remaining = shipped(出库负数) - returned(回仓正数)
    仅用于“订单详情”展示；列表使用聚合 SQL（性能更好）。
    """
    wh_cond = ""
    params: dict = {
        "ref": order_ref,
        "reasons": list(SHIP_OUT_REASONS),
        "receipt_reason": "RECEIPT",
        "days": int(days),
    }
    if warehouse_id is not None:
        wh_cond = "AND warehouse_id = :wid"
        params["wid"] = int(warehouse_id)

    sql = f"""
    WITH shipped AS (
      SELECT COALESCE(SUM(-delta), 0)::int AS shipped_total
        FROM stock_ledger
       WHERE ref = :ref
         AND delta < 0
         AND reason = ANY(:reasons)
         AND occurred_at >= now() - (:days || ' days')::interval
         {wh_cond}
    ),
    returned AS (
      SELECT COALESCE(SUM(delta), 0)::int AS returned_total
        FROM stock_ledger
       WHERE ref = :ref
         AND delta > 0
         AND reason = :receipt_reason
         AND occurred_at >= now() - (:days || ' days')::interval
         {wh_cond}
    )
    SELECT GREATEST((SELECT shipped_total FROM shipped) - (SELECT returned_total FROM returned), 0)::int AS remaining_qty
    """
    row = (await session.execute(sa.text(sql), params)).mappings().first()
    if not row:
        return None
    return int(row.get("remaining_qty") or 0)
