# app/api/routers/warehouses_service_provinces_routes.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.warehouses_service_provinces_schemas import (
    WarehouseServiceProvincesOut,
    WarehouseServiceProvincesPutIn,
)


def register(router: APIRouter) -> None:
    @router.get(
        "/warehouses/{warehouse_id}/service-provinces",
        response_model=WarehouseServiceProvincesOut,
    )
    async def get_service_provinces(
        warehouse_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> WarehouseServiceProvincesOut:
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
        provinces: List[str] = []
        seen = set()
        for p in data.provinces or []:
            p2 = (p or "").strip()
            if not p2:
                continue
            if p2 in seen:
                continue
            seen.add(p2)
            provinces.append(p2)

        # 全量替换：同一事务里先删后插
        await session.execute(
            sa.text("DELETE FROM warehouse_service_provinces WHERE warehouse_id = :wid"),
            {"wid": int(warehouse_id)},
        )

        if provinces:
            for p in provinces:
                try:
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
                            VALUES (:wid, :p)
                            """
                        ),
                        {"wid": int(warehouse_id), "p": p},
                    )
                except Exception:
                    # 关键：插入失败后事务已处于 aborted 状态，必须先 rollback
                    await session.rollback()

                    owner = (
                        await session.execute(
                            sa.text(
                                """
                                SELECT warehouse_id
                                  FROM warehouse_service_provinces
                                 WHERE province_code = :p
                                 LIMIT 1
                                """
                            ),
                            {"p": p},
                        )
                    ).scalar_one_or_none()

                    if owner is not None and int(owner) != int(warehouse_id):
                        raise HTTPException(
                            status_code=409,
                            detail=f"省份互斥冲突：{p} 已属于仓库 {int(owner)}，无法绑定到仓库 {int(warehouse_id)}",
                        )

                    raise HTTPException(
                        status_code=400,
                        detail=f"保存失败：省份 {p} 写入失败（请检查仓库是否存在或省份配置冲突）",
                    )

        await session.commit()
        return WarehouseServiceProvincesOut(warehouse_id=int(warehouse_id), provinces=provinces)
