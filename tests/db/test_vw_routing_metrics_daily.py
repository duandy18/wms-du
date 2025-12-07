"""
合约测试：vw_routing_metrics_daily

验证点：
- 基于 orders.created_at 做 day 聚合
- 按 (platform, shop_id, route_mode, warehouse_id) 聚合
- routed_orders: warehouse_id 非空的订单数
- failed_orders: warehouse_id 为空的订单数
"""

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def _insert_store(
    session: AsyncSession, *, platform: str, shop_id: str, route_mode: str
) -> None:
    await session.execute(
        sa.text(
            """
            INSERT INTO stores (platform, shop_id, name, route_mode, created_at, updated_at)
            VALUES (:p, :s, :name, :mode, now(), now())
            ON CONFLICT (platform, shop_id) DO UPDATE
                SET route_mode = EXCLUDED.route_mode
            """
        ),
        {
            "p": platform,
            "s": shop_id,
            "name": f"{platform}-{shop_id}",
            "mode": route_mode,
        },
    )


async def _insert_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    created_at: datetime,
    warehouse_id: int | None,
) -> None:
    await session.execute(
        sa.text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                ext_order_no,
                status,
                buyer_name,
                buyer_phone,
                order_amount,
                pay_amount,
                created_at,
                updated_at,
                warehouse_id
            )
            VALUES (
                :p, :s, :o,
                'CREATED',
                'buyer', '13800000000',
                '10', '10',
                :at, :at,
                :wid
            )
            """
        ),
        {
            "p": platform,
            "s": shop_id,
            "o": ext_order_no,
            "at": created_at,
            "wid": warehouse_id,
        },
    )


@pytest.mark.asyncio
async def test_vw_routing_metrics_daily_basic(
    db_session_like_pg: AsyncSession,
) -> None:
    """
    构造以下场景：

    stores:
      - PDD/1, route_mode=FALLBACK

    orders (同一天):
      - ord1: wh=1
      - ord2: wh=1
      - ord3: wh=NULL (未路由成功)

    预期视图中整体：
      - routed_orders 总和 = 2
      - failed_orders 总和 = 1
      - route_mode 统一为 FALLBACK（来自 stores.route_mode）
    """
    session: AsyncSession = db_session_like_pg

    day = datetime(2025, 11, 19, 8, 0, 0, tzinfo=timezone.utc)

    # 1) 准备 store
    await _insert_store(session, platform="PDD", shop_id="1", route_mode="FALLBACK")

    # 2) 准备三条订单，两条成功路由，一条失败（warehouse_id=NULL）
    await _insert_order(
        session,
        platform="PDD",
        shop_id="1",
        ext_order_no="ORD-1",
        created_at=day,
        warehouse_id=1,
    )
    await _insert_order(
        session,
        platform="PDD",
        shop_id="1",
        ext_order_no="ORD-2",
        created_at=day,
        warehouse_id=1,
    )
    await _insert_order(
        session,
        platform="PDD",
        shop_id="1",
        ext_order_no="ORD-3",
        created_at=day,
        warehouse_id=None,
    )

    await session.commit()

    # 3) 查询视图
    rows = await session.execute(
        sa.text(
            """
            SELECT
                day,
                platform,
                shop_id,
                route_mode,
                warehouse_id,
                routed_orders,
                failed_orders
              FROM vw_routing_metrics_daily
             WHERE platform = :p
               AND shop_id  = :s
             ORDER BY warehouse_id NULLS LAST
            """
        ),
        {"p": "PDD", "s": "1"},
    )
    data = rows.fetchall()

    # 至少要有两行（一个 wh=1，一个 wh=NULL 分组）
    assert len(data) >= 2

    # 汇总检查整体的 routed/failed 之和
    total_routed = sum(int(r[5]) for r in data)
    total_failed = sum(int(r[6]) for r in data)

    assert total_routed == 2
    assert total_failed == 1

    # 检查 route_mode 是否按 stores.route_mode 回填
    route_modes = {r[3] for r in data}
    assert route_modes == {"FALLBACK"}
