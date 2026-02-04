# tests/services/pick/_seed_orders.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# ✅ Test constants (legacy exports kept for compatibility)
# ============================================================================
PLATFORM = "PDD"
SHOP_ID = "1"
WAREHOUSE_ID = 1


@dataclass(frozen=True)
class BlueprintOrderSeed:
    order_id: int
    ref: str
    platform: str
    shop_id: str
    ext_order_no: str


async def insert_min_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    warehouse_id: Optional[int] = None,
    fulfillment_status: str = "READY_TO_FULFILL",
    status: str = "CREATED",
    trace_id: Optional[str] = None,
) -> int:
    """
    ✅ 一步到位迁移后（测试 helper 口径）：

    - orders：只承载订单头（不再有 warehouse_id / fulfillment_status 等履约列）
    - order_fulfillment：承载执行仓/履约快照（最小事实）
        - actual_warehouse_id：执行仓事实（参数 warehouse_id 写到这里）
        - fulfillment_status：履约状态
        - blocked_reasons：本 helper 不写（保持 NULL）

    注意：本函数只插订单头与履约快照，不插 order_items。
    """
    plat = (platform or "").upper().strip()
    sid = str(shop_id or "").strip()
    ext = str(ext_order_no or "").strip()
    if not plat or not sid or not ext:
        raise ValueError("insert_min_order: platform/shop_id/ext_order_no must be non-empty")

    # 1) orders：只插订单头（幂等）
    row = await session.execute(
        text(
            """
            INSERT INTO orders (platform, shop_id, ext_order_no, status, trace_id, created_at, updated_at)
            VALUES (:p, :s, :ext, :st, :tid, now(), now())
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET status = EXCLUDED.status,
                  trace_id = COALESCE(EXCLUDED.trace_id, orders.trace_id),
                  updated_at = now()
            RETURNING id
            """
        ),
        {"p": plat, "s": sid, "ext": ext, "st": str(status), "tid": trace_id},
    )
    order_id = int(row.scalar_one())

    # 2) order_fulfillment：写执行仓/履约状态（最小事实）
    await session.execute(
        text(
            """
            INSERT INTO order_fulfillment (
              order_id,
              planned_warehouse_id,
              actual_warehouse_id,
              fulfillment_status,
              blocked_reasons,
              updated_at
            )
            VALUES (
              :oid,
              NULL,
              :awid,
              :fs,
              NULL,
              now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET actual_warehouse_id = EXCLUDED.actual_warehouse_id,
                   fulfillment_status  = EXCLUDED.fulfillment_status,
                   blocked_reasons     = NULL,
                   updated_at          = now()
            """
        ),
        {
            "oid": int(order_id),
            "awid": int(warehouse_id) if warehouse_id is not None else None,
            "fs": str(fulfillment_status),
        },
    )

    return int(order_id)


async def insert_orders_bulk(
    session: AsyncSession,
    *,
    orders: Sequence[Dict[str, Any]],
) -> list[int]:
    """
    批量插入订单（用于某些蓝皮书/基线测试）。
    注意：此函数只插订单头+履约快照，不插 items（由调用方视需要补齐）。
    """
    out: list[int] = []
    for o in orders:
        oid = await insert_min_order(
            session,
            platform=str(o.get("platform") or PLATFORM),
            shop_id=str(o.get("shop_id") or SHOP_ID),
            ext_order_no=str(o.get("ext_order_no") or ""),
            warehouse_id=(int(o["warehouse_id"]) if o.get("warehouse_id") is not None else None),
            fulfillment_status=str(o.get("fulfillment_status") or "READY_TO_FULFILL"),
            status=str(o.get("status") or "CREATED"),
            trace_id=(str(o["trace_id"]) if o.get("trace_id") else None),
        )
        out.append(int(oid))
    return out
