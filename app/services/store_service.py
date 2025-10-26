# app/services/store_service.py
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from sqlalchemy import select, func, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store, StoreItem, ChannelInventory
from app.models.stock import Stock  # 物理库存（单仓阶段：全仓总和）


class StoreService:
    """
    渠道侧薄服务（Phase 0 / v1.0）：
    - 读核心域（stocks）计算店铺可见量（A 策略），并可选择将结果落回 channel_inventory.visible_qty
    - 维护店铺/内品的绑定关系
    - 预留 warehouse_id 形参（单仓阶段忽略；多仓时启用）
    """

    # ---------------------------------------------------------------------
    # Store / StoreItem 基础维护
    # ---------------------------------------------------------------------

    @staticmethod
    async def ensure_store(
        session: AsyncSession, *, name: str, platform: str = "pdd", active: bool = True
    ) -> int:
        """按 (platform, name) 确保店铺存在，返回 store_id。"""
        row = (
            await session.execute(
                select(Store.id).where(Store.platform == platform, Store.name == name)
            )
        ).scalar_one_or_none()
        if row:
            return int(row)

        rid = (
            await session.execute(
                insert(Store)
                .values(name=name, platform=platform, active=active)
                .returning(Store.id)
            )
        ).scalar_one()
        await session.commit()
        return int(rid)

    @staticmethod
    async def upsert_store_item(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        pdd_sku_id: Optional[str] = None,
        outer_id: Optional[str] = None,
    ) -> int:
        """确保 (store_id, item_id) 的映射存在；可更新平台侧 sku/outer_id。"""
        existed = (
            await session.execute(
                select(StoreItem.id).where(
                    StoreItem.store_id == store_id, StoreItem.item_id == item_id
                )
            )
        ).scalar_one_or_none()
        if existed:
            await session.execute(
                update(StoreItem)
                .where(StoreItem.id == int(existed))
                .values(pdd_sku_id=pdd_sku_id, outer_id=outer_id)
            )
            await session.commit()
            return int(existed)

        rid = (
            await session.execute(
                insert(StoreItem)
                .values(
                    store_id=store_id, item_id=item_id, pdd_sku_id=pdd_sku_id, outer_id=outer_id
                )
                .returning(StoreItem.id)
            )
        ).scalar_one()
        await session.commit()
        return int(rid)

    # ---------------------------------------------------------------------
    # A 策略：计算与影子刷新
    #   available_total = Σ(stocks.qty) - Σ(all stores reserved_qty)
    #   headroom = ∞ if cap is NULL else (cap - reserved_of_this_store)
    #   visible = max(0, min(available_total, headroom))
    # ---------------------------------------------------------------------

    @staticmethod
    async def _sum_physical_qty(session: AsyncSession, *, item_id: int) -> int:
        """全仓物理数量总和：SUM(stocks.qty)"""
        q = select(func.coalesce(func.sum(Stock.qty), 0)).where(Stock.item_id == item_id)
        return int((await session.execute(q)).scalar_one() or 0)

    @staticmethod
    async def _sum_reserved_all_stores(session: AsyncSession, *, item_id: int) -> int:
        """所有店对该 item 的占用总和：SUM(channel_inventory.reserved_qty)"""
        q = select(func.coalesce(func.sum(ChannelInventory.reserved_qty), 0)).where(
            ChannelInventory.item_id == item_id
        )
        return int((await session.execute(q)).scalar_one() or 0)

    @staticmethod
    async def _ensure_ci_row(session: AsyncSession, *, store_id: int, item_id: int) -> int:
        """确保 channel_inventory 行存在，返回其 id。"""
        rid = (
            await session.execute(
                select(ChannelInventory.id).where(
                    ChannelInventory.store_id == store_id,
                    ChannelInventory.item_id == item_id,
                )
            )
        ).scalar_one_or_none()
        if rid:
            return int(rid)

        rid = (
            await session.execute(
                insert(ChannelInventory)
                .values(store_id=store_id, item_id=item_id, reserved_qty=0, visible_qty=0)
                .returning(ChannelInventory.id)
            )
        ).scalar_one()
        await session.commit()
        return int(rid)

    @staticmethod
    async def _get_ci_tuple(
        session: AsyncSession, *, store_id: int, item_id: int
    ) -> tuple[Optional[int], int]:
        """返回 (cap_qty, reserved_qty_of_store)。"""
        row = (
            await session.execute(
                select(ChannelInventory.cap_qty, ChannelInventory.reserved_qty).where(
                    ChannelInventory.store_id == store_id,
                    ChannelInventory.item_id == item_id,
                )
            )
        ).first()
        if row is None:
            return (None, 0)
        cap = row[0] if row[0] is not None else None
        reserved_store = int(row[1] or 0)
        return (cap, reserved_store)

    @staticmethod
    def _compute_visible(
        *,
        physical_total: int,
        reserved_all_stores: int,
        cap_qty: Optional[int],
        reserved_of_store: int,
    ) -> int:
        available_total = max(0, int(physical_total) - int(reserved_all_stores))
        if cap_qty is None:
            headroom = available_total
        else:
            headroom = max(0, int(cap_qty) - int(reserved_of_store))
        return max(0, min(available_total, headroom))

    @staticmethod
    async def refresh_channel_inventory_for_store(
        session: AsyncSession,
        *,
        store_id: int,
        item_ids: Sequence[int] | None = None,
        dry_run: bool = False,
        warehouse_id: int | None = None,  # 预留（v1.0 忽略）
    ) -> dict:
        """
        影子刷新：计算店内各 item 的 visible。
        dry_run=True 仅返回计算结果；False 时把 visible_qty 落表。
        返回 {store_id, items:[{item_id, physical, reserved_all, cap, reserved_store, visible}], updated, dry_run}
        """
        # 选出该店已绑定的内品集合
        q = select(StoreItem.item_id).where(StoreItem.store_id == store_id)
        if item_ids:
            q = q.where(StoreItem.item_id.in_(list(item_ids)))
        bound = [int(r[0]) for r in (await session.execute(q)).all()]
        if not bound:
            return {"store_id": store_id, "items": [], "updated": 0, "dry_run": dry_run}

        out_items: list[dict] = []
        updated = 0

        for iid in bound:
            # 确保有 CI 行（便于读取 cap/reserved）
            await StoreService._ensure_ci_row(session, store_id=store_id, item_id=iid)

            physical = await StoreService._sum_physical_qty(session, item_id=iid)
            reserved_all = await StoreService._sum_reserved_all_stores(session, item_id=iid)
            cap, reserved_store = await StoreService._get_ci_tuple(session, store_id=store_id, item_id=iid)

            visible = StoreService._compute_visible(
                physical_total=physical,
                reserved_all_stores=reserved_all,
                cap_qty=cap,
                reserved_of_store=reserved_store,
            )

            out_items.append(
                {
                    "item_id": iid,
                    "physical": physical,
                    "reserved_all": reserved_all,
                    "cap": cap,
                    "reserved_store": reserved_store,
                    "visible": visible,
                }
            )

            if not dry_run:
                await session.execute(
                    update(ChannelInventory)
                    .where(
                        ChannelInventory.store_id == store_id,
                        ChannelInventory.item_id == iid,
                    )
                    .values(visible_qty=visible)
                )
                updated += 1

        if not dry_run:
            await session.commit()

        return {"store_id": store_id, "items": out_items, "updated": updated, "dry_run": dry_run}

    # ---------------------------------------------------------------------
    # 影子对比：把已落表的 visible_qty 与实时计算结果对齐（用于日常体检）
    # ---------------------------------------------------------------------

    @staticmethod
    async def shadow_compare_with_snapshot(
        session: AsyncSession, *, store_id: int
    ) -> list[dict]:
        """
        对比 channel_inventory.visible_qty 与 A 策略实时计算的结果。
        返回 [{item_id, expected, channel, delta}]
        """
        items = [
            int(r[0])
            for r in (
                await session.execute(
                    select(StoreItem.item_id).where(StoreItem.store_id == store_id)
                )
            ).all()
        ]
        out: list[dict] = []
        for iid in items:
            physical = await StoreService._sum_physical_qty(session, item_id=iid)
            reserved_all = await StoreService._sum_reserved_all_stores(session, item_id=iid)
            cap, reserved_store = await StoreService._get_ci_tuple(session, store_id=store_id, item_id=iid)
            expected = StoreService._compute_visible(
                physical_total=physical,
                reserved_all_stores=reserved_all,
                cap_qty=cap,
                reserved_of_store=reserved_store,
            )
            channel_v = (
                await session.execute(
                    select(ChannelInventory.visible_qty).where(
                        ChannelInventory.store_id == store_id,
                        ChannelInventory.item_id == iid,
                    )
                )
            ).scalar_one_or_none()
            channel_v = int(channel_v or 0)
            out.append({"item_id": iid, "expected": expected, "channel": channel_v, "delta": channel_v - expected})
        return out
