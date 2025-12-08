# tests/services/test_order_reserve_anti_oversell.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService

UTC = timezone.utc


async def _pick_one_stock_item(session: AsyncSession):
    """
    尝试从当前基线中挑一个 (item_id, warehouse_id, available) 出来。
    若没有可用库存，直接 skip 测试，避免猜表结构乱插数据。
    """
    row = await session.execute(
        text(
            """
            SELECT item_id, warehouse_id, SUM(qty) AS qty
            FROM stocks
            GROUP BY item_id, warehouse_id
            ORDER BY item_id, warehouse_id
            LIMIT 1
            """
        )
    )
    r = row.first()
    if not r:
        pytest.skip("当前测试基线中没有 stocks 记录，无法验证 anti-oversell")
    item_id, warehouse_id, qty = int(r[0]), int(r[1]), int(r[2])
    if qty <= 0:
        pytest.skip("当前测试基线 stocks.qty <= 0，无法验证 anti-oversell")
    return item_id, warehouse_id, qty


async def _ensure_order_row(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    warehouse_id: int,
) -> str:
    """
    为给定 platform/shop_id/ext_order_no 插入一条最小化订单头（带 warehouse_id），
    返回标准化的 order_ref = ORD:{PLAT}:{shop_id}:{ext_order_no}
    """
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
            "tid": f"TRACE-{plat}-{shop_id}-{ext_order_no}",
            "created_at": now,
        },
    )
    return f"ORD:{plat}:{shop_id}:{ext_order_no}"


@pytest.mark.asyncio
async def test_reserve_succeeds_when_available_enough(session: AsyncSession):
    """
    available 充足时，reserve 应成功落入 reservations，并正确扣减可售库存。

    升级版语义：
      - 先插入一条订单（带 warehouse_id）；
      - 使用标准 ref=ORD:PLAT:shop:ext_order_no 调用 OrderService.reserve；
      - anti-oversell 由 OrderReserveFlow + SoftReserveService 负责。
    """
    item_id, warehouse_id, _ = await _pick_one_stock_item(session)

    platform = "PDD"
    shop_id = "SHOP1"
    ext_order_no = "RESERVE-OK-1"
    order_ref = await _ensure_order_row(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=warehouse_id,
    )

    channel_svc = ChannelInventoryService()

    # 基线 available
    available0 = await channel_svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    if available0 <= 1:
        pytest.skip(f"baseline available={available0}，太小无法测试差量")

    reserve_qty = max(1, available0 // 2)

    # 执行 reserve（订单驱动 soft-reserve）
    r = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": item_id, "qty": reserve_qty}],
    )
    assert r["status"] == "OK"
    assert r.get("reservation_id") is not None

    # 再查 available，应减少 reserve_qty
    available1 = await channel_svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    assert available1 == available0 - reserve_qty


@pytest.mark.asyncio
async def test_reserve_rejects_when_insufficient_available(session: AsyncSession):
    """
    当已存在一部分 soft reserve 时，第二笔超出剩余 available 的占用应被拒绝。

    仍然基于订单驱动的 Golden Flow：
      - 为每个 ref 插入对应订单头（带 warehouse_id）；
      - 使用 ORD:... ref 调用 OrderService.reserve；
      - anti-oversell 由 OrderReserveFlow 内部的 ChannelInventoryService 校验。
    """
    item_id, warehouse_id, _ = await _pick_one_stock_item(session)

    platform = "PDD"
    shop_id = "SHOP1"
    ext1 = "RESERVE-OK-2A"
    ext2 = "RESERVE-FAIL-2B"

    order_ref1 = await _ensure_order_row(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext1,
        warehouse_id=warehouse_id,
    )
    order_ref2 = await _ensure_order_row(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext2,
        warehouse_id=warehouse_id,
    )

    channel_svc = ChannelInventoryService()

    # baseline available
    available0 = await channel_svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    if available0 <= 3:
        pytest.skip(f"baseline available={available0}，太小无法构造超售场景")

    # 第一步：占用一部分（成功）
    first_qty = available0 - 2  # 留出 2，方便后面超限
    r1 = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref1,
        lines=[{"item_id": item_id, "qty": first_qty}],
    )
    assert r1["status"] == "OK"

    available_after_first = await channel_svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    # 理论上 == 2
    assert available_after_first == available0 - first_qty

    # 第二步：尝试再占用比剩余多 1 的数量，应抛异常
    second_qty = available_after_first + 1
    with pytest.raises(ValueError) as ei:
        await OrderService.reserve(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=order_ref2,
            lines=[{"item_id": item_id, "qty": second_qty}],
        )
    msg = str(ei.value)
    assert "insufficient available" in msg
    assert f"item={item_id}" in msg


@pytest.mark.asyncio
async def test_reserve_idempotent_same_qty(session: AsyncSession):
    """
    同一 ref 重放同样的 lines 时，应视为幂等：
    - 第一次建 open reservation；
    - 第二次不会再做可售校验（增量为 0），也不会抛错；
    - reservation_id 应保持不变。

    这里的 ref = ORD:{PLAT}:{shop_id}:{ext_order_no}，依旧是订单驱动软预占。
    """
    item_id, warehouse_id, _ = await _pick_one_stock_item(session)

    platform = "PDD"
    shop_id = "SHOP1"
    ext_order_no = "RESERVE-IDEMP-3"
    order_ref = await _ensure_order_row(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=warehouse_id,
    )

    channel_svc = ChannelInventoryService()

    available0 = await channel_svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    if available0 <= 1:
        pytest.skip(f"baseline available={available0}，太小无法测试")

    qty = max(1, available0 // 2)

    # 第一次 reserve
    r1 = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": item_id, "qty": qty}],
    )
    assert r1["status"] == "OK"
    rid1 = r1.get("reservation_id")
    assert rid1 is not None

    # 第二次重放同样的 ref + qty
    r2 = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": item_id, "qty": qty}],
    )
    assert r2["status"] == "OK"
    rid2 = r2.get("reservation_id")
    assert rid2 == rid1  # 同一业务键，幂等返回相同 reservation
