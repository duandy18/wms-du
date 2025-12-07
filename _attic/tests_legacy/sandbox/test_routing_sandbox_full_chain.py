import pytest

pytest.skip(
    "legacy outbound_v2/event_gateway tests (disabled on v2 baseline)", allow_module_level=True
)

# tests/sandbox/test_routing_sandbox_full_chain.py

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Tuple

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService
from app.services.outbound_v2_service import OutboundV2Service
from app.services.ship_service import ShipService
from app.services.stock_service import StockService

UTC = timezone.utc


@dataclass
class SandboxOrderLine:
    item_id: int
    qty: int


@dataclass
class SandboxOrder:
    platform: str
    shop_id: str
    ext_order_id: str
    lines: List[SandboxOrderLine]


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


async def seed_world_full_chain(session: AsyncSession) -> None:
    """
    全链路沙盘的世界初始化：

    - 仓库：1,2,3
    - 店铺：
        S1: FALLBACK, main=WH1, backup=WH2
        S2: STRICT_TOP, main=WH2
        S3: FALLBACK, main=WH3
    - items: 1001,1002,1003（带 sku）
    - 库存：用 StockService.adjust 预先种一批库存（每仓每 item +1000）
    """

    # 仓
    await session.execute(
        sa.text(
            """
            INSERT INTO warehouses (id, name)
            VALUES
                (1, 'WH1'),
                (2, 'WH2'),
                (3, 'WH3')
            ON CONFLICT (id) DO NOTHING;
            """
        )
    )

    # 店 + route_mode
    await session.execute(
        sa.text(
            """
            INSERT INTO stores (platform, shop_id, name, route_mode, created_at, updated_at)
            VALUES
                ('PDD','S1','S1','FALLBACK',now(),now()),
                ('PDD','S2','S2','STRICT_TOP',now(),now()),
                ('PDD','S3','S3','FALLBACK',now(),now())
            ON CONFLICT (platform, shop_id) DO NOTHING;
            """
        )
    )

    # store_warehouse 绑定
    await session.execute(
        sa.text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            SELECT s.id, w.warehouse_id, w.is_top, w.priority
              FROM stores s,
                   (VALUES
                        ('S1',1,true,1),
                        ('S1',2,false,2),
                        ('S2',2,true,1),
                        ('S3',3,true,1)
                   ) AS w(shop, warehouse_id, is_top, priority)
             WHERE s.shop_id = w.shop
               AND s.platform = 'PDD'
            ON CONFLICT DO NOTHING;
            """
        )
    )

    # items（带 sku，避免 NOT NULL）
    await session.execute(
        sa.text(
            """
            INSERT INTO items (id, sku, name)
            VALUES
                (1001,'SKU-1001','item1001'),
                (1002,'SKU-1002','item1002'),
                (1003,'SKU-1003','item1003')
            ON CONFLICT (id) DO NOTHING;
            """
        )
    )

    # 用 StockService.adjust 预先种库存
    stock_svc = StockService()
    now = datetime.now(UTC)
    today = date.today()
    expiry = today + timedelta(days=365)

    # 每仓每 item +1000，batch_code= "B-{wh}-{item}"，保证沙盘期间不会被扣空
    for wh in (1, 2, 3):
        for item_id in (1001, 1002, 1003):
            await stock_svc.adjust(
                session=session,
                item_id=item_id,
                warehouse_id=wh,
                delta=1000,
                reason="UT_FULLCHAIN_SEED",
                ref=f"SEED-{wh}-{item_id}",
                ref_line=1,
                occurred_at=now,
                batch_code=f"B-{wh}-{item_id}",
                production_date=today,
                expiry_date=expiry,
                trace_id="TRACE-FULLCHAIN-SEED",
            )

    await session.commit()


def generate_orders(n: int) -> List[SandboxOrder]:
    """
    全链路沙盘使用的订单生成。
    """
    shops = ["S1", "S2", "S3"]
    items = [1001, 1002, 1003]

    orders: List[SandboxOrder] = []
    for i in range(n):
        shop = random.choice(shops)
        lines: List[SandboxOrderLine] = [
            SandboxOrderLine(item_id=random.choice(items), qty=random.randint(1, 5))
            for _ in range(random.randint(1, 3))
        ]
        orders.append(
            SandboxOrder(
                platform="PDD",
                shop_id=shop,
                ext_order_id=f"FULLCHAIN-{i:04d}",
                lines=lines,
            )
        )
    return orders


async def run_full_pipeline(
    session: AsyncSession,
    orders: List[SandboxOrder],
) -> None:
    """
    全链路： ingest -> reserve -> outbound_v2.commit -> ShipService.commit

    策略：
    - trace_id: 每单一个 trace_id = TRACE-FC-{platform}-{shop}-{ext_order_id}
    - outbound_v2 行：
        * warehouse_id: 取 orders.warehouse_id 路由结果
        * batch_code: 用 seed_world_full_chain 里的 "B-{wh}-{item}" 模式
    """

    order_svc = OrderService()
    outbound_svc = OutboundV2Service()
    ship_svc = ShipService()

    now = datetime.now(UTC)

    for o in orders:
        trace_id = f"TRACE-FC-{o.platform}-{o.shop_id}-{o.ext_order_id}"

        # 1) ingest（路由 + ORDER_CREATED + WAREHOUSE_ROUTED + routing metrics）
        ingest_res = await order_svc.ingest(
            session,
            platform=o.platform,
            shop_id=o.shop_id,
            ext_order_no=o.ext_order_id,
            items=[{"item_id": line.item_id, "qty": line.qty} for line in o.lines],
            trace_id=trace_id,
        )
        order_ref = ingest_res["ref"]
        order_id = ingest_res["id"]

        # 查订单仓（由 ingest 时路由写入 orders.warehouse_id）
        row = await session.execute(
            sa.text(
                """
                SELECT warehouse_id
                  FROM orders
                 WHERE id = :oid
                """
            ),
            {"oid": order_id},
        )
        wh = row.scalar()
        if not wh:
            # 没路由成功，跳过 reserve + ship，这单视为 FAIL_ROUTING
            continue
        wh = int(wh)

        # 2) reserve（占用）——用订单行重放
        await order_svc.reserve(
            session,
            platform=o.platform,
            shop_id=o.shop_id,
            ref=order_ref,
            lines=[{"item_id": line.item_id, "qty": line.qty} for line in o.lines],
            trace_id=trace_id,
        )

        # 3) outbound v2 出库（简化：使用 seed 时的批次编码）
        outbound_lines = [
            {
                "warehouse_id": wh,
                "item_id": line.item_id,
                "batch_code": f"B-{wh}-{line.item_id}",
                "qty": line.qty,
            }
            for line in o.lines
        ]

        await outbound_svc.commit(
            session,
            trace_id=trace_id,
            platform=o.platform,
            shop_id=o.shop_id,
            ref=order_ref,
            external_order_ref=o.ext_order_id,
            lines=outbound_lines,
            occurred_at=now,
        )

        # 4) ShipService 审计（SHIP_COMMIT）
        await ship_svc.commit(
            session,
            ref=order_ref,
            occurred_at=now,
            platform=o.platform,
            shop_id=o.shop_id,
            trace_id=trace_id,
        )

    await session.commit()


async def collect_routing_vs_ship_summary(
    session: AsyncSession,
) -> Dict[str, object]:
    """
    汇总“规划路由 vs 实际出库”：

    - routing: 来自 vw_routing_metrics_daily
    - ship_qty_by_wh: 来自 stock_ledger（reason = OUTBOUND_V2_SHIP）
    """

    # 路由结果
    rows_routing = await session.execute(
        sa.text(
            """
            SELECT platform,
                   shop_id,
                   route_mode,
                   warehouse_id,
                   routed_orders,
                   failed_orders
              FROM vw_routing_metrics_daily
             ORDER BY platform, shop_id, warehouse_id;
            """
        )
    )
    routing = rows_routing.fetchall()

    # 实际出库量（按仓聚合）
    rows_ship = await session.execute(
        sa.text(
            """
            SELECT warehouse_id,
                   SUM(CASE WHEN delta < 0 THEN -delta ELSE 0 END) AS ship_qty
              FROM stock_ledger
             WHERE reason = 'OUTBOUND_V2_SHIP'
             GROUP BY warehouse_id
             ORDER BY warehouse_id;
            """
        )
    )
    ship_rows = rows_ship.fetchall()
    ship_map: Dict[int, int] = {
        int(row[0]): int(row[1] or 0) for row in ship_rows if row[0] is not None
    }

    return {
        "routing": routing,
        "ship_qty_by_wh": ship_map,
    }


# ---------------------------------------------------------
# Full-chain Sandbox Test
# ---------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_sandbox_full_chain(
    db_session_like_pg: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Phase 4 全链路沙盘（ingest -> reserve -> outbound_v2 -> ship）：

    验证点：
    - vw_routing_metrics_daily 中出现的“有 routed_orders 的仓”，在 stock_ledger 中
      的 OUTBOUND_V2_SHIP 至少有一定的 ship_qty。
    - 即：规划路由到的仓，真实出库也真的从这些仓扣货，而不是“路由归这个仓，
      实际货从别处走”。

    注意：
    - 使用 fake ChannelInventoryService.get_available_for_item 来放宽可用量，
      避免 reserve 阶段因防超卖而抛错；
    - fallback / 失败场景已经在 ingest-only 沙盘中覆盖，这里只看“规划 vs 实际”。
    """

    session = db_session_like_pg

    random.seed(2025_11_19)

    await seed_world_full_chain(session)

    # ---- fake ChannelInventoryService.get_available_for_item ----
    # 全链路沙盘这里不再模拟缺货，只要不阻塞 reserve/ingest 即可。
    # 重点是后面对比：routing metrics 中的仓 vs ledger 中的扣减仓。

    async def fake_get_available_for_item(
        self,
        session: AsyncSession,  # type: ignore[override]
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        # 给一个远大于订单行最大 qty 的数字，避免 anti-oversell 抛错
        return 10_000

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available_for_item,
        raising=False,
    )

    # ---- 执行全链路 ----
    orders = generate_orders(100)
    await run_full_pipeline(session, orders)

    summary = await collect_routing_vs_ship_summary(session)

    routing = summary["routing"]
    ship_qty_by_wh: Dict[int, int] = summary["ship_qty_by_wh"]

    print("\n=== Full-chain Routing vs Ship Summary ===")
    print("[Routing]")
    for r in routing:
        print(r)
    print("[Ship by WH]")
    print(ship_qty_by_wh)

    # 路由到的仓（有 routed_orders>0 且 warehouse_id 非空）
    routed_wh_ids = {
        int(r.warehouse_id)
        for r in routing
        if getattr(r, "warehouse_id", None) is not None and int(r.routed_orders) > 0
    }

    # 至少有一个仓真的被路由到
    assert routed_wh_ids, "expected at least one warehouse to be routed"

    # 对每个被路由的仓，应该在 ledger 中有 OUTBOUND_V2_SHIP 的发货量 > 0
    missing: List[Tuple[int, int]] = []
    for wid in routed_wh_ids:
        qty = ship_qty_by_wh.get(wid, 0)
        if qty <= 0:
            missing.append((wid, qty))

    assert not missing, f"some routed warehouses have no OUTBOUND_V2_SHIP qty: {missing}"
