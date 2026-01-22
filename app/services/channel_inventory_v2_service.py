from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reservation import Reservation
from app.models.reservation_line import ReservationLine
from app.models.stock import Stock
from app.models.store import Store, StoreWarehouse


@dataclass
class WarehouseAvailabilityV2:
    """
    单仓维度可售信息 (platform, shop_id, warehouse_id, item_id).

    说明：
    - 这是“展示视图”数据结构，用于 UI 展示、诊断、解释；
    - 不是“履约裁决”入口。
    """

    warehouse_id: int
    is_top: bool
    is_default: bool
    priority: int
    on_hand_qty: int
    reserved_qty: int
    available_qty: int


@dataclass
class ChannelAvailabilityV2:
    """
    多仓汇总可售信息（展示视图，不带路由策略）.

    说明：
    - 仓集合只取 store_warehouse 中绑定的仓；
    - reserved 这里是“按 platform/shop_id 过滤后的 open reservation 锁量”（展示用途）；
    - 不用于 Phase 4.x 的“事实裁决”（事实裁决请走 StockAvailabilityService + WarehouseRouter）。
    """

    platform: str
    shop_id: str
    item_id: int
    total_on_hand: int
    total_reserved: int
    total_available: int
    per_warehouse: List[WarehouseAvailabilityV2]


class StoreNotFoundError(RuntimeError):
    """店铺不存在（platform + shop_id）时抛出，用于 API 侧转 404."""

    pass


class ChannelInventoryV2Service:
    """
    ⚠️ 展示视图服务（不是履约事实裁决器）

    口径（展示用）：
        维度：platform, shop_id, warehouse_id, item_id
        on_hand   = SUM(stocks.qty)
        reserved  = SUM(reservation_line.qty - reservation_line.consumed_qty)
                   在满足 TTL / 状态的前提下（并按 platform/shop_id 过滤）
        available = max(on_hand - reserved, 0)

    说明：
        - 仓的集合只取 store_warehouse 中绑定的仓；
        - 不依赖 channel_inventory 表（那张表只是 legacy 可见层/配置层）；
        - 不处理 route_mode，路由策略由路由服务决定；
        - Phase 4.x 的“是否可履约”判断不得从这里发起。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- Public API ----------

    async def get_store_item_availability(
        self,
        *,
        platform: str,
        shop_id: str,
        item_id: int,
    ) -> ChannelAvailabilityV2:
        """
        计算某店铺下某 item 在各仓的展示型可售情况（store_warehouse 绑定仓范围）。

        返回：
            ChannelAvailabilityV2：
                - total_on_hand / total_reserved / total_available
                - per_warehouse：按 StoreWarehouse.priority 排序
        """
        store_id = await self._get_store_id(platform=platform, shop_id=shop_id)
        store_warehouses = await self._get_store_warehouses(store_id=store_id)

        if not store_warehouses:
            # 没有绑定任何仓，直接返回 0
            return ChannelAvailabilityV2(
                platform=platform,
                shop_id=shop_id,
                item_id=item_id,
                total_on_hand=0,
                total_reserved=0,
                total_available=0,
                per_warehouse=[],
            )

        warehouse_ids = [sw.warehouse_id for sw in store_warehouses]

        on_hand_by_wh = await self._get_on_hand_by_warehouse(
            warehouse_ids=warehouse_ids,
            item_id=item_id,
        )
        reserved_by_wh = await self._get_reserved_by_warehouse(
            platform=platform,
            shop_id=shop_id,
            warehouse_ids=warehouse_ids,
            item_id=item_id,
        )

        per_warehouse: List[WarehouseAvailabilityV2] = []
        total_on_hand = 0
        total_reserved = 0
        total_available = 0

        # 严格按 StoreWarehouse.priority 排序后的顺序构造结果
        for sw in store_warehouses:
            wh_id = sw.warehouse_id
            oh = on_hand_by_wh.get(wh_id, 0)
            rv = reserved_by_wh.get(wh_id, 0)
            av = max(oh - rv, 0)

            total_on_hand += oh
            total_reserved += rv
            total_available += av

            per_warehouse.append(
                WarehouseAvailabilityV2(
                    warehouse_id=wh_id,
                    is_top=sw.is_top,
                    is_default=sw.is_default,
                    priority=sw.priority,
                    on_hand_qty=oh,
                    reserved_qty=rv,
                    available_qty=av,
                )
            )

        return ChannelAvailabilityV2(
            platform=platform,
            shop_id=shop_id,
            item_id=item_id,
            total_on_hand=total_on_hand,
            total_reserved=total_reserved,
            total_available=total_available,
            per_warehouse=per_warehouse,
        )

    # ---------- Private helpers ----------

    async def _get_store_id(self, *, platform: str, shop_id: str) -> int:
        """
        按 platform + shop_id 查店铺 id，只认 active=True 的店。
        """
        stmt: Select = (
            select(Store.id)
            .where(Store.platform == platform)
            .where(Store.shop_id == shop_id)
            .where(Store.active.is_(True))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        row = res.first()
        if row is None:
            raise StoreNotFoundError(f"Store not found: {platform}/{shop_id}")
        return int(row.id)

    async def _get_store_warehouses(self, *, store_id: int) -> List[StoreWarehouse]:
        """
        获取店铺绑定的仓列表，按 priority 升序。
        不做 is_active 过滤，因为当前模型没有该字段。
        """
        stmt: Select = (
            select(StoreWarehouse)
            .where(StoreWarehouse.store_id == store_id)
            .order_by(StoreWarehouse.priority.asc(), StoreWarehouse.id.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def _get_on_hand_by_warehouse(
        self,
        *,
        warehouse_ids: List[int],
        item_id: int,
    ) -> Dict[int, int]:
        """
        按仓汇总 stocks.qty 作为 on_hand。
        """
        if not warehouse_ids:
            return {}

        stmt: Select = (
            select(
                Stock.warehouse_id,
                func.coalesce(func.sum(Stock.qty), 0).label("on_hand_qty"),
            )
            .where(Stock.item_id == item_id)
            .where(Stock.warehouse_id.in_(warehouse_ids))
            .group_by(Stock.warehouse_id)
        )
        res = await self.session.execute(stmt)
        rows = res.all()
        return {int(row.warehouse_id): int(row.on_hand_qty) for row in rows}

    async def _get_reserved_by_warehouse(
        self,
        *,
        platform: str,
        shop_id: str,
        warehouse_ids: List[int],
        item_id: int,
    ) -> Dict[int, int]:
        """
        按仓汇总 Soft Reserve 锁量（展示口径，按 platform/shop 过滤）：

            reserved = SUM(line.qty - line.consumed_qty)

        过滤条件（保守口径）：
            - Reservation.platform = :platform
            - Reservation.shop_id = :shop_id
            - Reservation.warehouse_id IN (:warehouse_ids)
            - Reservation.status = 'open'
            - ReservationLine.status = 'open'
            - Reservation.released_at IS NULL
            - Reservation.expire_at IS NULL OR Reservation.expire_at > now()
        """
        if not warehouse_ids:
            return {}

        stmt: Select = (
            select(
                Reservation.warehouse_id,
                func.coalesce(
                    func.sum((ReservationLine.qty - ReservationLine.consumed_qty).cast(func.int4)),
                    0,
                ).label("reserved_qty"),
            )
            .join(ReservationLine, ReservationLine.reservation_id == Reservation.id)
            .where(Reservation.platform == platform)
            .where(Reservation.shop_id == shop_id)
            .where(Reservation.warehouse_id.in_(warehouse_ids))
            .where(ReservationLine.item_id == item_id)
            .where(Reservation.status == "open")
            .where(ReservationLine.status == "open")
            .where(Reservation.released_at.is_(None))
            .where((Reservation.expire_at.is_(None)) | (Reservation.expire_at > func.now()))
            .group_by(Reservation.warehouse_id)
        )

        res = await self.session.execute(stmt)
        rows = res.all()
        return {int(row.warehouse_id): int(row.reserved_qty) for row in rows}
