# tests/sandbox/test_routing_sandbox_multi_warehouse.py

import random
from dataclasses import dataclass
from typing import List

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService


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


async def seed_world(session: AsyncSession) -> None:
    """
    第一版沙盘的初始化世界：
    - 仓库：1,2,3
    - 店铺：S1(FALLBACK), S2(STRICT_TOP), S3(FALLBACK)
    - store_warehouse 绑定关系
    - items：1001,1002,1003（带 SKU）
    """

    # 确保 1/2/3 仓存在（只插必要字段）
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

    # 插店铺（route_mode 与我们路由策略保持一致）
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

    # store_warehouse 绑定：
    #  S1: main=1, backup=2
    #  S2: main=2 (STRICT_TOP)
    #  S3: main=3 (无备仓)
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

    # items（必须包含 sku，避免 NOT NULL 失败）
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

    await session.commit()


def generate_orders(n: int) -> List[SandboxOrder]:
    """
    随机生成订单（只跑 ingest）。
    为了可复现，外部调用前应设定 random.seed。
    """
    shops = ["S1", "S2", "S3"]
    items = [1001, 1002, 1003]

    orders: List[SandboxOrder] = []
    for i in range(n):
        shop = random.choice(shops)
        lines = [
            SandboxOrderLine(item_id=random.choice(items), qty=random.randint(1, 8))
            for _ in range(random.randint(1, 3))
        ]
        orders.append(
            SandboxOrder(
                platform="PDD",
                shop_id=shop,
                ext_order_id=f"SANDBOX-{i:04d}",
                lines=lines,
            )
        )
    return orders


async def collect_sql_summary(session: AsyncSession):
    """
    从 vw_routing_metrics_daily 提取路由结果（ingest-only）
    """
    res = await session.execute(
        sa.text(
            """
            SELECT platform, shop_id, route_mode, warehouse_id,
                   routed_orders, failed_orders
              FROM vw_routing_metrics_daily
             ORDER BY platform, shop_id, warehouse_id;
            """
        )
    )
    return res.fetchall()


# ---------------------------------------------------------
# Test
# ---------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_sandbox_ingest_only(
    db_session_like_pg: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    第一版沙盘：只跑 ingest，不碰 reserve/ship。

    通过 fake ChannelInventoryService.get_available_for_item 模拟：
    - S1(FALLBACK)：主仓1小库存、备仓2大库存 -> 会出现 fallback
    - S2(STRICT_TOP)：仓2大库存 -> 全部落仓2，不失败
    - S3(FALLBACK)：仅仓3，小库存 -> 会出现 failed（no_candidate）
    """

    session = db_session_like_pg

    # 固定随机种子，确保结果可重复
    random.seed(2025_11_19)

    await seed_world(session)

    # ---- fake ChannelInventoryService.get_available_for_item ----

    # key: (platform, shop_id, warehouse_id) -> capacity（每个订单可用量）
    # 注意：这里不模拟扣减，只是决定“这一单能不能在该仓整单履约”。
    capacity_map = {
        ("PDD", "S1", 1): 5,  # S1 主仓1，小容量
        ("PDD", "S1", 2): 999,  # S1 备仓2，大容量
        ("PDD", "S2", 2): 999,  # S2 主仓2，充足
        ("PDD", "S3", 3): 3,  # S3 主仓3，小容量，制造失败
    }

    async def fake_get_available_for_item(
        self,
        session: AsyncSession,  # type: ignore[override]
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        # 忽略 item_id，按 (平台,店铺,仓) 粗粒度模拟
        key = (platform.upper(), str(shop_id), int(warehouse_id))
        return capacity_map.get(key, 0)

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available_for_item,
        raising=False,
    )

    # ---- 批量 ingest ----

    orders = generate_orders(200)

    for order in orders:
        await OrderService.ingest(
            session,
            platform=order.platform,
            shop_id=order.shop_id,
            ext_order_no=order.ext_order_id,
            items=[{"item_id": line.item_id, "qty": line.qty} for line in order.lines],
        )

    await session.commit()

    summary = await collect_sql_summary(session)

    print("\n=== Routing Sandbox Summary (Ingest Only) ===")
    for row in summary:
        print(row)

    # ----------------------
    # S2（STRICT_TOP）验证
    # ----------------------
    s2_rows = [r for r in summary if r.shop_id == "S2"]
    # S2 只有仓2，route_mode=STRICT_TOP，容量很大，不应失败
    for r in s2_rows:
        assert r.route_mode == "STRICT_TOP"
        assert r.warehouse_id == 2
        assert r.failed_orders == 0

    # ----------------------
    # S1（FALLBACK）验证
    # ----------------------
    s1_rows = [r for r in summary if r.shop_id == "S1"]
    total_s1_orders = sum(r.routed_orders + r.failed_orders for r in s1_rows)
    fallback_s1 = sum(r.routed_orders for r in s1_rows if r.warehouse_id == 2)
    # 有订单，且出现过 fallback -> 仓2分担了部分订单
    assert total_s1_orders > 0
    assert fallback_s1 > 0

    # ----------------------
    # S3（FALLBACK + 小库存）验证
    # ----------------------
    s3_rows = [r for r in summary if r.shop_id == "S3"]
    failed_s3 = sum(r.failed_orders for r in s3_rows)
    # 容量很小，随机订单中应出现无仓可履约的情况
    assert failed_s3 > 0
