# app/services/master_data.py
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession


class MasterDataService:
    """
    只负责：主数据最小化兜底（warehouses/locations/items）与仓库查询。
    不做审计，不做业务。
    """

    async def ensure_baseline(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int = 1,
        location_ids: Iterable[int],
        item_ids: Iterable[int],
    ) -> int:
        """
        幂等兜底：
        - 确保 warehouse / locations / items 最小集存在；
        - 返回首个位置对应的 warehouse_id（若查询不到则回退为默认）。
        """
        await self._ensure_warehouse(session, warehouse_id=warehouse_id)
        first_valid_loc_id = await self._ensure_locations(session, warehouse_id=warehouse_id, location_ids=location_ids)
        await self._ensure_items(session, item_ids=item_ids)

        if first_valid_loc_id is not None:
            row = await session.execute(
                SA("SELECT warehouse_id FROM locations WHERE id=:i"),
                {"i": first_valid_loc_id},
            )
            result = row.scalar()
            return result or warehouse_id
        return warehouse_id

    async def _ensure_warehouse(self, session: AsyncSession, *, warehouse_id: int) -> None:
        await session.execute(
            SA("INSERT INTO warehouses(id,name) VALUES (:i,'WH-1') ON CONFLICT (id) DO NOTHING"),
            {"i": warehouse_id},
        )

    async def _ensure_locations(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        location_ids: Iterable[int],
    ) -> Optional[int]:
        first_valid_loc_id: Optional[int] = None
        for loc_raw in location_ids:
            try:
                loc = int(loc_raw)
            except Exception:
                continue
            if loc <= 0:
                continue

            if first_valid_loc_id is None:
                first_valid_loc_id = loc

            await session.execute(
                SA(
                    "INSERT INTO locations(id, warehouse_id, code, name) "
                    "VALUES (:l, :w, :c, :n) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"l": loc, "w": warehouse_id, "c": f"LOC-{loc}", "n": f"LOC-{loc}"},
            )
        return first_valid_loc_id

    async def _ensure_items(self, session: AsyncSession, *, item_ids: Iterable[int]) -> None:
        """
        ✅ 注意：items.sku 视为不可变身份码（后端权威）：
        - baseline 兜底只保证 id 存在；
        - 冲突时绝不更新 sku（禁止“后门改码”）；
        - 允许更新 name（作为兜底描述）。
        """
        for it_raw in item_ids:
            try:
                it = int(it_raw)
            except Exception:
                continue
            if it <= 0:
                continue

            await session.execute(
                SA(
                    "INSERT INTO items(id, sku, name) VALUES (:i, :s, :n) "
                    "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name"
                ),
                {"i": it, "s": f"SKU-{it}", "n": f"ITEM-{it}"},
            )
