# app/wms/warehouses/routers/warehouses_routes_service_provinces.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.wms.warehouses.contracts.warehouses_service_provinces import (
    WarehouseServiceProvinceOccupancyOut,
    WarehouseServiceProvinceOccupancyRow,
    WarehouseServiceProvincesOut,
    WarehouseServiceProvincesPutIn,
)


def _normalize_provinces(raw: List[str]) -> List[str]:
    provinces: List[str] = []
    seen = set()
    for p in raw or []:
        p2 = (p or "").strip()
        if not p2:
            continue
        if p2 in seen:
            continue
        seen.add(p2)
        provinces.append(p2)
    provinces.sort()
    return provinces


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
    @router.get(
        "/warehouses/service-provinces/occupancy",
        response_model=WarehouseServiceProvinceOccupancyOut,
    )
    async def get_service_provinces_occupancy(
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceProvinceOccupancyOut:
        rows = (
            await session.execute(
                sa.text(
                    """
                    SELECT province_code, warehouse_id
                      FROM warehouse_service_provinces
                     ORDER BY province_code
                    """
                )
            )
        ).all()

        out_rows = [
            WarehouseServiceProvinceOccupancyRow(
                province_code=str(r[0]),
                warehouse_id=int(r[1]),
            )
            for r in rows
        ]
        return WarehouseServiceProvinceOccupancyOut(rows=out_rows)

    @router.get(
        "/warehouses/{warehouse_id}/service-provinces",
        response_model=WarehouseServiceProvincesOut,
    )
    async def get_service_provinces(
        warehouse_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceProvincesOut:
        await _ensure_warehouse_exists(session, int(warehouse_id))

        rows = (
            await session.execute(
                sa.text(
                    """
                    SELECT province_code
                      FROM warehouse_service_provinces
                     WHERE warehouse_id = :wid
                     ORDER BY province_code
                    """
                ),
                {"wid": int(warehouse_id)},
            )
        ).all()
        provinces = [r[0] for r in rows]
        return WarehouseServiceProvincesOut(warehouse_id=int(warehouse_id), provinces=provinces)

    @router.put(
        "/warehouses/{warehouse_id}/service-provinces",
        response_model=WarehouseServiceProvincesOut,
    )
    async def put_service_provinces(
        warehouse_id: int,
        data: WarehouseServiceProvincesPutIn,
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceProvincesOut:
        wid = int(warehouse_id)
        await _ensure_warehouse_exists(session, wid)

        provinces = _normalize_provinces(list(data.provinces or []))

        if provinces:
            conflict_rows = (
                await session.execute(
                    sa.text(
                        """
                        SELECT province_code, warehouse_id
                          FROM warehouse_service_provinces
                         WHERE province_code = ANY(:provinces)
                           AND warehouse_id <> :wid
                         ORDER BY province_code
                        """
                    ),
                    {"provinces": provinces, "wid": wid},
                )
            ).all()

            if conflict_rows:
                conflicts = [
                    {"province": str(r[0]), "owner_warehouse_id": int(r[1])} for r in conflict_rows
                ]
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "省份互斥冲突：部分省份已属于其他仓库，无法绑定。",
                        "warehouse_id": wid,
                        "conflicts": conflicts,
                    },
                )

        await session.execute(
            sa.text("DELETE FROM warehouse_service_provinces WHERE warehouse_id = :wid"),
            {"wid": wid},
        )

        if provinces:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
                    SELECT :wid, x
                      FROM unnest(CAST(:provinces AS text[])) AS x
                    """
                ),
                {"wid": wid, "provinces": provinces},
            )

        await session.commit()
        return WarehouseServiceProvincesOut(warehouse_id=wid, provinces=provinces)
