# tests/services/pick/_helpers_pick_blueprint.py
from __future__ import annotations

from ._client_pick_api import (  # 拆分：HTTP 调用集中到单独文件
    commit_pick_task as _commit_pick_task,
    create_pick_task_from_order,
    get_pick_task,
    scan_pick,
)
from ._seed_order_items import (  # 拆分：order_items 写入策略与 item 选择
    ensure_order_has_items as _ensure_order_has_items,
    pick_any_item_id as _pick_any_item_id,
)
from ._seed_orders import (  # re-export：保持旧 import 路径不变
    PLATFORM,
    SHOP_ID,
    WAREHOUSE_ID,
    BlueprintOrderSeed,
    insert_min_order,
    insert_orders_bulk,
)
from ._utils_pick import (  # 拆分：杂项工具集中
    build_handoff_code,
    force_no_stock,
    get_task_ref,
    ledger_count,
    stocks_count,
)

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_pickable_order(
    session: AsyncSession,
    *,
    warehouse_id: int = WAREHOUSE_ID,
    platform: str = PLATFORM,
    shop_id: str = SHOP_ID,
    ext_order_no: Optional[str] = None,
    trace_id: Optional[str] = None,
    item_id: Optional[int] = None,
    qty: int = 1,
) -> int:
    """
    兼容入口：确保存在一张“可拣货订单”并具备执行仓事实 + 至少一条商品行。

    重要：这里必须 COMMIT。
    原因：多数 API 测试是“DB session 造数据 + http client 调 API（服务端新 session）”的组合，
    若不提交，服务端看不到订单，会返回 422（订单不存在）。
    """
    import uuid

    ext = ext_order_no or f"UT-PICK-BLUEPRINT-{uuid.uuid4().hex[:12]}"
    oid = await insert_min_order(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext,
        warehouse_id=int(warehouse_id),
        fulfillment_status="READY_TO_FULFILL",
        status="CREATED",
        trace_id=trace_id,
    )

    iid = int(item_id) if item_id is not None else await _pick_any_item_id(session)
    await _ensure_order_has_items(session, order_id=int(oid), item_id=iid, qty=int(qty))

    await session.commit()
    return int(oid)


async def pick_any_item_id(session: AsyncSession) -> int:
    # 兼容旧 API：仍然暴露 pick_any_item_id，但实现已搬到 _seed_order_items.py
    return await _pick_any_item_id(session)


async def commit_pick_task(
    client_like,
    *,
    task_id: int,
    platform: str = PLATFORM,
    shop_id: str = SHOP_ID,
    handoff_code: Optional[str] = None,
    trace_id: Optional[str] = None,
    allow_diff: bool = True,
):
    # 兼容旧签名：handoff_code 当前未入参到 API payload（保持历史行为）
    _ = handoff_code
    return await _commit_pick_task(
        client_like,
        task_id=int(task_id),
        platform=str(platform),
        shop_id=str(shop_id),
        trace_id=(str(trace_id) if trace_id else None),
        allow_diff=bool(allow_diff),
    )
