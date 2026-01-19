# app/api/routers/warehouses_service_cities_routes.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.warehouses_service_cities_schemas import (
    WarehouseServiceCitiesOut,
    WarehouseServiceCitiesPutIn,
    WarehouseServiceCityOccupancyOut,
    WarehouseServiceCityOccupancyRow,
)


def _normalize_cities(raw: List[str]) -> List[str]:
    cities: List[str] = []
    seen = set()
    for c in raw or []:
        c2 = (c or "").strip()
        if not c2:
            continue
        if c2 in seen:
            continue
        seen.add(c2)
        cities.append(c2)
    cities.sort()
    return cities


async def _ensure_warehouse_exists(session: AsyncSession, warehouse_id: int) -> None:
    row = await session.execute(
        sa.text(
            """
            SELECT 1
              FROM warehouses
             WHERE id = :wid
             LIMIT 1
            """
        ),
        {"wid": int(warehouse_id)},
    )
    if row.first() is None:
        raise HTTPException(status_code=404, detail="warehouse not found")


def register(router: APIRouter) -> None:
    # ---------------------------
    # City Occupancy（只读）
    # ---------------------------
    @router.get(
        "/warehouses/service-cities/occupancy",
        response_model=WarehouseServiceCityOccupancyOut,
    )
    async def get_service_cities_occupancy(
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceCityOccupancyOut:
        rows = (
            await session.execute(
                sa.text(
                    """
                    SELECT city_code, warehouse_id
                      FROM warehouse_service_cities
                     ORDER BY city_code
                    """
                )
            )
        ).all()

        out_rows = [
            WarehouseServiceCityOccupancyRow(
                city_code=str(r[0]),
                warehouse_id=int(r[1]),
            )
            for r in rows
        ]
        return WarehouseServiceCityOccupancyOut(rows=out_rows)

    # ---------------------------
    # 单仓查询
    # ---------------------------
    @router.get(
        "/warehouses/{warehouse_id}/service-cities",
        response_model=WarehouseServiceCitiesOut,
    )
    async def get_service_cities(
        warehouse_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceCitiesOut:
        await _ensure_warehouse_exists(session, int(warehouse_id))

        rows = (
            await session.execute(
                sa.text(
                    """
                    SELECT city_code
                      FROM warehouse_service_cities
                     WHERE warehouse_id = :wid
                     ORDER BY city_code
                    """
                ),
                {"wid": int(warehouse_id)},
            )
        ).all()
        cities = [r[0] for r in rows]
        return WarehouseServiceCitiesOut(warehouse_id=int(warehouse_id), cities=cities)

    # ---------------------------
    # 单仓全量替换（同事务）
    # ---------------------------
    @router.put(
        "/warehouses/{warehouse_id}/service-cities",
        response_model=WarehouseServiceCitiesOut,
    )
    async def put_service_cities(
        warehouse_id: int,
        data: WarehouseServiceCitiesPutIn,
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceCitiesOut:
        wid = int(warehouse_id)
        await _ensure_warehouse_exists(session, wid)

        cities = _normalize_cities(list(data.cities or []))

        # 1) 预检查：城市是否已被其他仓占用（全局互斥）
        if cities:
            conflict_rows = (
                await session.execute(
                    sa.text(
                        """
                        SELECT city_code, warehouse_id
                          FROM warehouse_service_cities
                         WHERE city_code = ANY(CAST(:cities AS text[]))
                           AND warehouse_id <> :wid
                         ORDER BY city_code
                        """
                    ),
                    {"cities": cities, "wid": wid},
                )
            ).all()

            if conflict_rows:
                conflicts = [{"city": str(r[0]), "owner_warehouse_id": int(r[1])} for r in conflict_rows]
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "城市互斥冲突：部分城市已属于其他仓库，无法绑定。",
                        "warehouse_id": wid,
                        "conflicts": conflicts,
                    },
                )

        # 2) 全量替换：同一事务里先删后插（批量写入）
        await session.execute(
            sa.text("DELETE FROM warehouse_service_cities WHERE warehouse_id = :wid"),
            {"wid": wid},
        )

        if cities:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO warehouse_service_cities (warehouse_id, city_code)
                    SELECT :wid, x
                      FROM unnest(CAST(:cities AS text[])) AS x
                    """
                ),
                {"wid": wid, "cities": cities},
            )

        await session.commit()
        return WarehouseServiceCitiesOut(warehouse_id=wid, cities=cities)
