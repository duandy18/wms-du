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
        # 1) 仓库兜底（幂等）
        await session.execute(
            SA("INSERT INTO warehouses(id,name) VALUES (:i,'WH-1') ON CONFLICT (id) DO NOTHING"),
            {"i": warehouse_id},
        )

        # 2) 位置兜底：保留“显式 id”，但一律用 ON CONFLICT (id) DO NOTHING，避免主键撞车
        first_valid_loc_id: Optional[int] = None
        for loc_raw in location_ids:
            try:
                loc = int(loc_raw)
            except Exception:
                continue
            if loc > 0:
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

        # 3) 商品兜底：同样一次性标准化
        for it_raw in item_ids:
            try:
                it = int(it_raw)
            except Exception:
                continue
            if it > 0:
                await session.execute(
                    SA(
                        "INSERT INTO items(id, sku, name) VALUES (:i, :s, :n) "
                        "ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name"
                    ),
                    {"i": it, "s": f"SKU-{it}", "n": f"ITEM-{it}"},
                )

        # 4) 返回首个有效库位对应的仓库 ID（若无则回退）
        if first_valid_loc_id is not None:
            row = await session.execute(
                SA("SELECT warehouse_id FROM locations WHERE id=:i"),
                {"i": first_valid_loc_id},
            )
            result = row.scalar()
            return result or warehouse_id
        return warehouse_id
