# tests/services/test_order_service.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot

from app.services.order_service import OrderService
from app.services.stock_availability_service import StockAvailabilityService

UTC = timezone.utc
pytestmark = pytest.mark.contract


async def _ensure_order_row(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    warehouse_id: int,
    trace_id: str,
) -> str:
    plat = platform.upper()
    now = datetime.now(UTC)
    await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                ext_order_no,
                warehouse_id,
                trace_id,
                created_at
            )
            VALUES (
                :p,
                :s,
                :o,
                :w,
                :tid,
                :created_at
            )
            ON CONFLICT (platform, shop_id, ext_order_no) DO NOTHING
            """
        ),
        {
            "p": plat,
            "s": shop_id,
            "o": ext_order_no,
            "w": warehouse_id,
            "tid": trace_id,
            "created_at": now,
        },
    )
    return f"ORD:{plat}:{shop_id}:{ext_order_no}"


@pytest.mark.asyncio
async def test_fefo_reserve_then_cancel(session: AsyncSession):
    """
    Phase 3.6+ 版合同（升级版）：

    场景：
      - 仓库 1 / 库位 1 / 商品 7301，有一批次 code='RES-7301'，qty=5
      - 平台 PDD / 店铺 SHOP1：
          * 基于真实订单（ORD:PDD:SHOP1:RES-TEST-7301）调用 OrderService.reserve 占用 2
          * 可售库存应从 available0 降到 available0-2
          * 调用 OrderService.cancel 取消该 ref
          * 可售库存应恢复为 available0

    注意：
      - reserve/cancel 统一走 Golden Flow：OrderReserveFlow + SoftReserveService；
      - 仓库依赖 orders.warehouse_id，而非拍脑袋传 warehouse_id。
      - 可售查询使用事实层：StockAvailabilityService（stocks - open reservations）
    """

    wh, loc, item, code = 1, 1, 7301, "RES-7301"

    # 1) 基线：准备仓/库位/商品 + 批次 + 库存槽位
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code=code, qty=5, days=365)
    await session.commit()

    # 2) 准备订单头（带 warehouse_id + trace_id）
    platform = "PDD"
    shop_id = "SHOP1"
    ext_order_no = "RES-TEST-7301"
    trace_id = f"TRACE-{ext_order_no}"

    order_ref = await _ensure_order_row(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=wh,
        trace_id=trace_id,
    )

    # 3) 读 baseline 可售库存（按平台/店铺/仓库）
    available0 = await StockAvailabilityService.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=wh,
        item_id=item,
    )

    # 至少有 5 件（我们刚 seed 了一批），但为了容忍已有基础数据，只要求 >=2
    assert available0 >= 2

    # 4) 调用 OrderService.reserve 占用 2 件
    r1 = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": item, "qty": 2}],
    )
    assert r1["status"] == "OK"
    assert r1.get("reservation_id") is not None
    await session.commit()

    available1 = await StockAvailabilityService.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=wh,
        item_id=item,
    )
    assert available1 == available0 - 2

    # 5) 调用 OrderService.cancel 取消该预留
    r2 = await OrderService.cancel(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": item, "qty": 2}],
    )
    assert r2["status"] in ("CANCELED", "NOOP")  # 在高并发/重放场景下允许 NOOP
    await session.commit()

    available2 = await StockAvailabilityService.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=wh,
        item_id=item,
    )

    # 最终可售应回到 baseline
    assert available2 == available0
