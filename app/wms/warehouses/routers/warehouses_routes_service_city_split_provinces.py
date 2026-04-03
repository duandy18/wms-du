# app/wms/warehouses/routers/warehouses_routes_service_city_split_provinces.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.wms.warehouses.contracts.warehouses_service_city_split_provinces import (
    WarehouseServiceCitySplitProvincesOut,
    WarehouseServiceCitySplitProvincesPutIn,
)


def _normalize(raw: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in raw or []:
        s = (x or "").strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    out.sort()
    return out


def register(router: APIRouter) -> None:
    @router.get(
        "/warehouses/service-provinces/city-split",
        response_model=WarehouseServiceCitySplitProvincesOut,
    )
    async def get_city_split_provinces(
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceCitySplitProvincesOut:
        rows = (
            await session.execute(
                sa.text(
                    """
                    SELECT province_code
                      FROM warehouse_service_city_split_provinces
                     ORDER BY province_code
                    """
                )
            )
        ).all()
        return WarehouseServiceCitySplitProvincesOut(provinces=[str(r[0]) for r in rows])

    @router.put(
        "/warehouses/service-provinces/city-split",
        response_model=WarehouseServiceCitySplitProvincesOut,
    )
    async def put_city_split_provinces(
        data: WarehouseServiceCitySplitProvincesPutIn,
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceCitySplitProvincesOut:
        provinces = _normalize(list(data.provinces or []))

        await session.execute(sa.text("DELETE FROM warehouse_service_city_split_provinces"))

        if provinces:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO warehouse_service_city_split_provinces (province_code)
                    SELECT x FROM unnest(CAST(:provinces AS text[])) AS x
                    """
                ),
                {"provinces": provinces},
            )
            await session.execute(
                sa.text(
                    """
                    DELETE FROM warehouse_service_provinces
                     WHERE province_code = ANY(:provinces)
                    """
                ),
                {"provinces": provinces},
            )

        await session.commit()
        return WarehouseServiceCitySplitProvincesOut(provinces=provinces)
