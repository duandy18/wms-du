# app/procurement/repos/purchase_order_source_options_repo.py
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _normalize_limit(limit: int | None) -> int:
    x = int(limit or 20)
    if x < 1:
        return 1
    if x > 50:
        return 50
    return x


async def list_purchase_order_source_options(
    session: AsyncSession,
    *,
    warehouse_id: int | None = None,
    q: str | None = None,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    """
    采购来源下拉窄读面。

    口径：
    - 一条 option = 一张采购单
    - 只返回仍可作为“采购入库来源”的采购单：
      * po.status = CREATED
      * 聚合后 total_remaining_base > 0
    - completion_status 由 purchase_order_line_completion 聚合得出
    """
    where_clauses = ["po.status = 'CREATED'"]
    params: dict[str, Any] = {
        "limit": _normalize_limit(limit),
    }

    if warehouse_id is not None:
        where_clauses.append("plc.warehouse_id = :warehouse_id")
        params["warehouse_id"] = int(warehouse_id)

    qv = (q or "").strip()
    if qv:
        where_clauses.append(
            """
            (
              plc.po_no ILIKE :q_like
              OR plc.supplier_name ILIKE :q_like
            )
            """.strip()
        )
        params["q_like"] = f"%{qv}%"

    where_sql = " AND ".join(where_clauses)

    sql = text(
        f"""
        SELECT
          plc.po_id AS po_id,
          plc.po_no AS po_no,
          plc.warehouse_id AS warehouse_id,
          plc.supplier_id AS supplier_id,
          plc.supplier_name AS supplier_name,
          plc.purchase_time AS purchase_time,
          po.status AS po_status,
          CASE
            WHEN COALESCE(SUM(plc.qty_received_base), 0) <= 0 THEN 'NOT_RECEIVED'
            WHEN COALESCE(SUM(plc.qty_remaining_base), 0) <= 0 THEN 'RECEIVED'
            ELSE 'PARTIAL'
          END AS completion_status,
          MAX(plc.last_received_at) AS last_received_at
        FROM purchase_order_line_completion plc
        JOIN purchase_orders po
          ON po.id = plc.po_id
        WHERE {where_sql}
        GROUP BY
          plc.po_id,
          plc.po_no,
          plc.warehouse_id,
          plc.supplier_id,
          plc.supplier_name,
          plc.purchase_time,
          po.status
        HAVING COALESCE(SUM(plc.qty_remaining_base), 0) > 0
        ORDER BY plc.purchase_time DESC, plc.po_id DESC
        LIMIT :limit
        """
    )

    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


__all__ = [
    "list_purchase_order_source_options",
]
