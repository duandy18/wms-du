from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService


@dataclass(frozen=True)
class OrderContext:
    platform: str
    shop_id: str
    order_id: str | int


@dataclass(frozen=True)
class OrderLine:
    item_id: int
    qty: int


@dataclass(frozen=True)
class StoreWarehouseBinding:
    platform: str
    shop_id: str
    warehouse_id: int
    is_top: bool
    priority: int


@dataclass(frozen=True)
class RoutingResult:
    platform: str
    shop_id: str
    order_id: str | int
    warehouse_id: int
    reason: str
    considered_warehouses: Tuple[int, ...]


class AvailabilityProvider(Protocol):
    async def get_available(
        self,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int: ...


class ChannelInventoryAvailabilityProvider(AvailabilityProvider):
    """
    唯一可售数据源：
      ChannelInventoryService.get_available_for_item(session, platform, shop_id, warehouse_id, item_id)

    注意：
    - 这里用“位置参数”调用，以兼容测试里 fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id)
      的 monkeypatch 签名。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._svc = ChannelInventoryService()

    async def get_available(
        self,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        # 位置参数调用，避免把 keyword 传给 fake_get_available 导致 TypeError
        v = await self._svc.get_available_for_item(
            self._session,
            platform,
            shop_id,
            warehouse_id,
            item_id,
        )
        # 路由只关心“够不够”，负数视为 0
        return v if v >= 0 else 0


class NoWarehouseConfigured(Exception):
    pass


class NoWarehouseCanFulfill(Exception):
    pass


class WarehouseRouter:
    """
    多仓路由核心逻辑（不跨仓、不拆单、不调拨）：
    - 仓集合来自 store_warehouse；
    - 可售来自唯一大脑 ChannelInventoryService；
    """

    def __init__(self, availability_provider: AvailabilityProvider) -> None:
        self._availability_provider = availability_provider

    async def route(
        self,
        ctx: OrderContext,
        lines: Sequence[OrderLine],
        bindings: Sequence[StoreWarehouseBinding],
    ) -> RoutingResult:
        if not bindings:
            raise NoWarehouseConfigured(
                f"No warehouse configured for platform={ctx.platform}, shop_id={ctx.shop_id}"
            )

        scoped = [b for b in bindings if b.platform == ctx.platform and b.shop_id == ctx.shop_id]
        if not scoped:
            raise NoWarehouseConfigured(
                f"No warehouse configured for platform={ctx.platform}, "
                f"shop_id={ctx.shop_id} (after scoping)"
            )

        avail_cache: Dict[Tuple[int, int], int] = {}

        async def _get_avail(wh: int, item: int) -> int:
            key = (wh, item)
            if key in avail_cache:
                return avail_cache[key]
            v = await self._availability_provider.get_available(
                platform=ctx.platform,
                shop_id=ctx.shop_id,
                warehouse_id=wh,
                item_id=item,
            )
            if v < 0:
                v = 0
            avail_cache[key] = v
            return v

        async def _can_fulfill(wh: int) -> bool:
            for line in lines:
                if line.qty <= 0:
                    continue
                if await _get_avail(wh, line.item_id) < line.qty:
                    return False
            return True

        top: list[StoreWarehouseBinding] = []
        backup: list[StoreWarehouseBinding] = []
        for b in scoped:
            (top if b.is_top else backup).append(b)

        def _sort_key(b: StoreWarehouseBinding) -> Tuple[int, int]:
            return (b.priority, b.warehouse_id)

        top.sort(key=_sort_key)
        backup.sort(key=_sort_key)

        considered: list[int] = []

        # 先尝试主仓
        for b in top:
            considered.append(b.warehouse_id)
            if await _can_fulfill(b.warehouse_id):
                return RoutingResult(
                    platform=ctx.platform,
                    shop_id=ctx.shop_id,
                    order_id=ctx.order_id,
                    warehouse_id=b.warehouse_id,
                    reason="top_warehouse_with_stock",
                    considered_warehouses=tuple(considered),
                )

        # 再尝试备仓
        for b in backup:
            considered.append(b.warehouse_id)
            if await _can_fulfill(b.warehouse_id):
                return RoutingResult(
                    platform=ctx.platform,
                    shop_id=ctx.shop_id,
                    order_id=ctx.order_id,
                    warehouse_id=b.warehouse_id,
                    reason="backup_warehouse_with_stock",
                    considered_warehouses=tuple(considered),
                )

        raise NoWarehouseCanFulfill(
            f"No warehouse can fulfill order={ctx.order_id} "
            f"for platform={ctx.platform}, shop_id={ctx.shop_id}. "
            f"Considered warehouses={considered or '[]'}"
        )
