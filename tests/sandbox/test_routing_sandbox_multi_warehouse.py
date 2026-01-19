# tests/sandbox/test_routing_sandbox_multi_warehouse.py

import random
from dataclasses import dataclass
from typing import List

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService

import app.services.order_ingest_service as order_ingest_service


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
    Route C 沙盘初始化世界：

    - 仓库：1,2,3
    - 店铺：S1, S2, S3（route_mode 字段仍写入，但 Route C 不依赖）
    - warehouse_service_provinces：省码 → 服务仓（S1/S2 映射到仓2；S3 故意不映射制造失败）
    - items：1001,1002,1003
    """
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

    # Route C：省→服务仓。S1/S2 映射到仓2；S3 故意不映射（制造 failed）
    await session.execute(sa.text("DELETE FROM warehouse_service_provinces WHERE province_code IN ('P-S1','P-S2','P-S3')"))
    await session.execute(
        sa.text(
            """
            INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
            VALUES
                (2, 'P-S1'),
                (2, 'P-S2')
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
    Route C 沙盘：只跑 ingest，不碰 reserve/ship。

    通过 fake ChannelInventoryService.get_available_for_item 模拟：
    - S1：省码命中仓2，但容量小 -> 会出现 routed + failed（INSUFFICIENT_QTY）
    - S2：省码命中仓2，容量大 -> 全部 routed
    - S3：省码不映射 -> 全部 failed（NO_SERVICE_WAREHOUSE）
    """
    session = db_session_like_pg

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    # ingest-only：避免 reserve_flow 干扰
    async def _noop_reserve_flow(*_, **__):
        return None

    monkeypatch.setattr(order_ingest_service, "reserve_flow", _noop_reserve_flow)

    random.seed(2025_11_19)
    await seed_world(session)

    # ---- fake ChannelInventoryService.get_available_for_item ----
    capacity_map = {
        ("PDD", "S1", 2): 5,    # S1 命中仓2但容量小 -> 一部分订单会失败
        ("PDD", "S2", 2): 999,  # S2 命中仓2容量足 -> 不失败
        # S3 没有省映射，函数即便返回也不会被调用到
    }

    async def fake_get_available_for_item(
        self,
        session: AsyncSession,  # type: ignore[override]
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        key = (platform.upper(), str(shop_id), int(warehouse_id))
        return capacity_map.get(key, 0)

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available_for_item,
        raising=False,
    )

    shop_province = {"S1": "P-S1", "S2": "P-S2", "S3": "P-S3"}

    orders = generate_orders(200)
    for order in orders:
        province = shop_province[order.shop_id]
        await OrderService.ingest(
            session,
            platform=order.platform,
            shop_id=order.shop_id,
            ext_order_no=order.ext_order_id,
            items=[{"item_id": line.item_id, "qty": line.qty} for line in order.lines],
            address={"province": province, "receiver_name": "X", "receiver_phone": "000"},
        )

    await session.commit()

    summary = await collect_sql_summary(session)

    print("\n=== Routing Sandbox Summary (Ingest Only / Route C) ===")
    for row in summary:
        print(row)

    # ----------------------
    # S2 验证：全部 routed 到仓2，failed_orders=0
    # ----------------------
    s2_rows = [r for r in summary if r.shop_id == "S2"]
    assert s2_rows, "no S2 rows in summary"
    for r in s2_rows:
        assert r.warehouse_id == 2
        assert r.failed_orders == 0

    # ----------------------
    # S1 验证：有 routed（仓2），且可能有 failed（warehouse_id 可能为 NULL 的分组）
    # ----------------------
    s1_rows = [r for r in summary if r.shop_id == "S1"]
    assert s1_rows, "no S1 rows in summary"
    total_s1_orders = sum(r.routed_orders + r.failed_orders for r in s1_rows)
    routed_s1_wh2 = sum(r.routed_orders for r in s1_rows if r.warehouse_id == 2)
    assert total_s1_orders > 0
    assert routed_s1_wh2 > 0

    # ----------------------
    # S3 验证：无省映射，应出现 failed
    # ----------------------
    s3_rows = [r for r in summary if r.shop_id == "S3"]
    assert s3_rows, "no S3 rows in summary"
    failed_s3 = sum(r.failed_orders for r in s3_rows)
    assert failed_s3 > 0
