# app/tms/records/repository.py
#
# 分拆说明：
# - 本文件承载 TMS / Records（物流台帐）只读查询；
# - 当前 shipping_records 已收口为“仓库交运事实”的 ledger；
# - 查询仅返回 ledger 本体字段，不混入状态域 / 对账域字段。
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SELECT_SHIPPING_RECORD_BASE = """
SELECT
  id,
  order_ref,
  platform,
  shop_id,
  warehouse_id,
  shipping_provider_id,
  carrier_code,
  carrier_name,
  tracking_no,
  gross_weight_kg,
  cost_estimated,
  dest_province,
  dest_city,
  created_at
FROM shipping_records
"""


async def get_shipping_record_by_id(
    session: AsyncSession,
    record_id: int,
) -> dict[str, object] | None:
    sql = text(
        f"""
        {_SELECT_SHIPPING_RECORD_BASE}
        WHERE id = :id
        """
    )
    row = (await session.execute(sql, {"id": record_id})).mappings().first()
    if row is None:
        return None
    return dict(row)


async def list_shipping_records_by_order_ref(
    session: AsyncSession,
    order_ref: str,
) -> list[dict[str, object]]:
    sql = text(
        f"""
        {_SELECT_SHIPPING_RECORD_BASE}
        WHERE order_ref = :order_ref
        ORDER BY created_at DESC, id DESC
        """
    )
    result = await session.execute(sql, {"order_ref": order_ref})
    rows = result.mappings().all()
    return [dict(row) for row in rows]
