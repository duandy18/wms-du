# app/services/warehouse_router.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_availability_service import StockAvailabilityService


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


# -----------------------------
# ✅ 统一“整单可履约检查”合同
# -----------------------------


@dataclass(frozen=True)
class InsufficientLine:
    item_id: int
    need: int
    available: int

    def to_dict(self) -> dict:
        return {"item_id": int(self.item_id), "need": int(self.need), "available": int(self.available)}


@dataclass(frozen=True)
class FulfillmentCheckResult:
    """
    整单同仓可履约检查输出合同（统一口径）：

    - status:
        OK       : 该仓可整单履约
        BLOCKED  : 该仓不可整单履约（insufficient 非空）
    - insufficient:
        缺口明细：[{item_id, need, available}]
    """

    status: str  # OK | BLOCKED
    warehouse_id: int
    insufficient: Tuple[InsufficientLine, ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": str(self.status),
            "warehouse_id": int(self.warehouse_id),
            "insufficient": [x.to_dict() for x in self.insufficient],
        }


class AvailabilityProvider(Protocol):
    async def get_available(
        self,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int: ...


class StockAvailabilityProvider(AvailabilityProvider):
    """
    ✅ 唯一可售数据源（事实层）：
      StockAvailabilityService.get_available_for_item(session, *, platform, shop_id, warehouse_id, item_id)

    说明：
    - get_available_for_item 的参数为 keyword-only；
    - UT monkeypatch 常用 fake_get_available(*_, **kwargs) 依赖 kwargs；
      因此必须使用 keyword 调用方式。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_available(
        self,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        v = await StockAvailabilityService.get_available_for_item(
            self._session,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
        )
        # 路由/可履约检查只关心“够不够”，负数视为 0
        return v if v >= 0 else 0


class NoWarehouseConfigured(Exception):
    pass


class NoWarehouseCanFulfill(Exception):
    pass


class WarehouseRouter:
    """
    多仓路由核心逻辑（不跨仓、不拆单、不调拨）：
    - 仓集合来自 store_warehouse（上游传入 bindings）；
    - 可售来自事实层 StockAvailabilityService；
    - ✅ “整单可履约检查”是事实层能力：统一由本类提供，其他地方不得自行判断。
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

    # ------------------------------------------------------------------
    # ✅ 统一出口：整单可履约检查（单仓）
    # ------------------------------------------------------------------

    async def check_whole_order(
        self,
        *,
        ctx: OrderContext,
        warehouse_id: int,
        lines: Sequence[OrderLine],
    ) -> FulfillmentCheckResult:
        wid = int(warehouse_id)
        if wid <= 0:
            return FulfillmentCheckResult(status="BLOCKED", warehouse_id=wid, insufficient=())

        avail_cache: Dict[Tuple[int, int], int] = {}

        async def _get_avail(item_id: int) -> int:
            key = (wid, int(item_id))
            if key in avail_cache:
                return avail_cache[key]
            v = await self._availability_provider.get_available(
                platform=ctx.platform,
                shop_id=ctx.shop_id,
                warehouse_id=wid,
                item_id=int(item_id),
            )
            if v < 0:
                v = 0
            avail_cache[key] = int(v)
            return int(v)

        insufficient: list[InsufficientLine] = []
        for line in lines:
            need = int(line.qty or 0)
            if need <= 0:
                continue
            item_id = int(line.item_id)
            available = await _get_avail(item_id)
            if need > int(available):
                insufficient.append(
                    InsufficientLine(item_id=item_id, need=need, available=int(available))
                )

        if insufficient:
            return FulfillmentCheckResult(
                status="BLOCKED",
                warehouse_id=wid,
                insufficient=tuple(insufficient),
            )
        return FulfillmentCheckResult(status="OK", warehouse_id=wid, insufficient=())

    # ------------------------------------------------------------------
    # ✅ 统一出口：整单可履约扫描（多仓，不选仓、不写库）
    # ------------------------------------------------------------------

    async def scan_warehouses(
        self,
        *,
        ctx: OrderContext,
        candidate_warehouse_ids: Sequence[int],
        lines: Sequence[OrderLine],
    ) -> Tuple[FulfillmentCheckResult, ...]:
        out: list[FulfillmentCheckResult] = []
        seen: set[int] = set()

        for raw_wid in candidate_warehouse_ids or []:
            wid = int(raw_wid)
            if wid <= 0 or wid in seen:
                continue
            seen.add(wid)
            r = await self.check_whole_order(ctx=ctx, warehouse_id=wid, lines=lines)
            out.append(r)

        return tuple(out)
