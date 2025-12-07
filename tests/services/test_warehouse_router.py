import pytest

from app.services.warehouse_router import (
    NoWarehouseCanFulfill,
    NoWarehouseConfigured,
    OrderContext,
    OrderLine,
    StoreWarehouseBinding,
    WarehouseRouter,
)


class FakeAvailabilityProvider:
    """
    简单的 in-memory 可用库存提供者，用于单元测试。
    key: (warehouse_id, item_id) -> qty
    """

    def __init__(self, data):
        self._data = data

    async def get_available(
        self,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        # 对于测试来说，忽略 platform / shop_id，只用 wh + item
        return int(self._data.get((warehouse_id, item_id), 0))


@pytest.mark.asyncio
async def test_route_prefers_top_warehouse_when_has_stock():
    """
    主仓有货、备仓也有货时，应优先主仓。
    """
    ctx = OrderContext(platform="PDD", shop_id="S1", order_id="O1")
    lines = [OrderLine(item_id=1, qty=5)]

    bindings = [
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=10, is_top=True, priority=10
        ),
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=20, is_top=False, priority=1
        ),
    ]

    avail = FakeAvailabilityProvider(
        {
            (10, 1): 10,  # 主仓有货
            (20, 1): 10,  # 备仓也有货
        }
    )

    router = WarehouseRouter(availability_provider=avail)

    result = await router.route(ctx, lines, bindings)

    assert result.warehouse_id == 10
    assert result.reason == "top_warehouse_with_stock"
    assert 10 in result.considered_warehouses


@pytest.mark.asyncio
async def test_route_fallback_to_backup_when_top_has_no_stock():
    """
    主仓库存不足时，应落到备仓（“主仓/备仓切换”场景）。
    """
    ctx = OrderContext(platform="PDD", shop_id="S1", order_id="O2")
    lines = [OrderLine(item_id=1, qty=5)]

    bindings = [
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=10, is_top=True, priority=10
        ),
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=20, is_top=False, priority=1
        ),
    ]

    avail = FakeAvailabilityProvider(
        {
            (10, 1): 2,  # 主仓没货 / 不足
            (20, 1): 10,  # 备仓足够
        }
    )

    router = WarehouseRouter(availability_provider=avail)

    result = await router.route(ctx, lines, bindings)

    assert result.warehouse_id == 20
    assert result.reason == "backup_warehouse_with_stock"
    # 确认路由过程两边都考虑过
    assert set(result.considered_warehouses) == {10, 20}


@pytest.mark.asyncio
async def test_route_respects_priority_within_top_group():
    """
    多个主仓时，按 priority 升序选择。
    """
    ctx = OrderContext(platform="PDD", shop_id="S1", order_id="O3")
    lines = [OrderLine(item_id=1, qty=5)]

    bindings = [
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=10, is_top=True, priority=20
        ),
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=11, is_top=True, priority=10
        ),
    ]

    avail = FakeAvailabilityProvider(
        {
            (10, 1): 10,
            (11, 1): 10,
        }
    )

    router = WarehouseRouter(availability_provider=avail)

    result = await router.route(ctx, lines, bindings)

    assert result.warehouse_id == 11  # priority 小的更优


@pytest.mark.asyncio
async def test_route_requires_full_order_fulfillment():
    """
    多行订单必须同仓全部满足，否则视为不可履约。
    """
    ctx = OrderContext(platform="PDD", shop_id="S1", order_id="O4")
    lines = [
        OrderLine(item_id=1, qty=5),
        OrderLine(item_id=2, qty=3),
    ]

    bindings = [
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=10, is_top=True, priority=10
        ),
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=20, is_top=False, priority=1
        ),
    ]

    avail = FakeAvailabilityProvider(
        {
            # 仓 10：只有 item 1 足够，item 2 不够
            (10, 1): 10,
            (10, 2): 1,
            # 仓 20：两行都足够
            (20, 1): 10,
            (20, 2): 10,
        }
    )

    router = WarehouseRouter(availability_provider=avail)

    result = await router.route(ctx, lines, bindings)

    assert result.warehouse_id == 20
    assert result.reason == "backup_warehouse_with_stock"


@pytest.mark.asyncio
async def test_no_warehouse_configured_raises():
    """
    无任何 store_warehouse 配置时，抛 NoWarehouseConfigured。
    """
    ctx = OrderContext(platform="PDD", shop_id="S1", order_id="O5")
    lines = [OrderLine(item_id=1, qty=5)]

    bindings = []  # 无配置

    avail = FakeAvailabilityProvider({})
    router = WarehouseRouter(availability_provider=avail)

    with pytest.raises(NoWarehouseConfigured):
        await router.route(ctx, lines, bindings)


@pytest.mark.asyncio
async def test_no_warehouse_can_fulfill_raises():
    """
    所有配置仓库存都不足时，抛 NoWarehouseCanFulfill（“库存不足 fallback”终止）。
    """
    ctx = OrderContext(platform="PDD", shop_id="S1", order_id="O6")
    lines = [OrderLine(item_id=1, qty=5)]

    bindings = [
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=10, is_top=True, priority=10
        ),
        StoreWarehouseBinding(
            platform="PDD", shop_id="S1", warehouse_id=20, is_top=False, priority=1
        ),
    ]

    avail = FakeAvailabilityProvider(
        {
            (10, 1): 2,  # 都不够
            (20, 1): 3,
        }
    )

    router = WarehouseRouter(availability_provider=avail)

    with pytest.raises(NoWarehouseCanFulfill):
        await router.route(ctx, lines, bindings)
