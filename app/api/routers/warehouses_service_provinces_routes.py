# app/api/routers/warehouses_service_provinces_routes.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.warehouses_service_provinces_schemas import (
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
    # ---------------------------
    # Province Occupancy（只读）
    # ---------------------------
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

    # ---------------------------
    # 单仓查询
    # ---------------------------
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

    # ---------------------------
    # 单仓全量替换（同事务）
    # ---------------------------
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

        # 1) 预检查：省份是否已被其他仓占用（全局互斥）
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

        # 2) 全量替换：同一事务里先删后插（批量写入）
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
