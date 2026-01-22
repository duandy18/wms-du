# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_warehouses.py
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme_warehouses_schemas import (
    SchemeWarehouseBindIn,
    SchemeWarehouseBindOut,
    SchemeWarehouseDeleteOut,
    SchemeWarehouseOut,
    SchemeWarehousePatchIn,
    SchemeWarehousePatchOut,
    SchemeWarehousesGetOut,
    WarehouseLiteOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def register(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/warehouses",
        response_model=SchemeWarehousesGetOut,
    )
    def get_scheme_warehouses(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ) -> SchemeWarehousesGetOut:
        check_perm(db, user, "config.store.read")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        # ✅ 合同：返回事实绑定 + warehouse 主数据（只读）
        sql = text(
            """
            SELECT
              sw.scheme_id,
              sw.warehouse_id,
              sw.active,
              w.id   AS w_id,
              w.name AS w_name,
              w.code AS w_code,
              w.active AS w_active
            FROM shipping_provider_pricing_scheme_warehouses sw
            JOIN warehouses w ON w.id = sw.warehouse_id
            WHERE sw.scheme_id = :sid
            ORDER BY sw.warehouse_id ASC
            """
        )
        rows = db.execute(sql, {"sid": int(scheme_id)}).mappings().all()

        data: List[SchemeWarehouseOut] = []
        for r in rows:
            wh = WarehouseLiteOut(
                id=int(r["w_id"]),
                name=str(r["w_name"]),
                code=(str(r["w_code"]) if r["w_code"] is not None else None),
                active=bool(r["w_active"]),
            )
            data.append(
                SchemeWarehouseOut(
                    scheme_id=int(r["scheme_id"]),
                    warehouse_id=int(r["warehouse_id"]),
                    active=bool(r["active"]),
                    warehouse=wh,
                )
            )

        return SchemeWarehousesGetOut(ok=True, data=data)

    @router.post(
        "/pricing-schemes/{scheme_id}/warehouses/bind",
        response_model=SchemeWarehouseBindOut,
    )
    def bind_scheme_warehouse(
        scheme_id: int = Path(..., ge=1),
        payload: SchemeWarehouseBindIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ) -> SchemeWarehouseBindOut:
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        # 校验 warehouse 存在
        sql_chk = text("SELECT id, name, code, active FROM warehouses WHERE id = :wid")
        wrow = db.execute(sql_chk, {"wid": int(payload.warehouse_id)}).mappings().first()
        if not wrow:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        # upsert（契约：幂等 bind）
        sql_upsert = text(
            """
            INSERT INTO shipping_provider_pricing_scheme_warehouses (scheme_id, warehouse_id, active)
            VALUES (:sid, :wid, :active)
            ON CONFLICT (scheme_id, warehouse_id)
            DO UPDATE SET active = EXCLUDED.active, updated_at = now()
            """
        )
        db.execute(
            sql_upsert,
            {"sid": int(scheme_id), "wid": int(payload.warehouse_id), "active": bool(payload.active)},
        )
        db.commit()

        wh = WarehouseLiteOut(
            id=int(wrow["id"]),
            name=str(wrow["name"]),
            code=(str(wrow["code"]) if wrow["code"] is not None else None),
            active=bool(wrow["active"]),
        )
        out = SchemeWarehouseOut(
            scheme_id=int(scheme_id),
            warehouse_id=int(payload.warehouse_id),
            active=bool(payload.active),
            warehouse=wh,
        )
        return SchemeWarehouseBindOut(ok=True, data=out)

    @router.patch(
        "/pricing-schemes/{scheme_id}/warehouses/{warehouse_id}",
        response_model=SchemeWarehousePatchOut,
    )
    def patch_scheme_warehouse(
        scheme_id: int = Path(..., ge=1),
        warehouse_id: int = Path(..., ge=1),
        payload: SchemeWarehousePatchIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ) -> SchemeWarehousePatchOut:
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        # 确保绑定存在
        sql_row = text(
            """
            SELECT
              sw.scheme_id,
              sw.warehouse_id,
              sw.active,
              w.id AS w_id,
              w.name AS w_name,
              w.code AS w_code,
              w.active AS w_active
            FROM shipping_provider_pricing_scheme_warehouses sw
            JOIN warehouses w ON w.id = sw.warehouse_id
            WHERE sw.scheme_id = :sid AND sw.warehouse_id = :wid
            """
        )
        row = db.execute(sql_row, {"sid": int(scheme_id), "wid": int(warehouse_id)}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Scheme warehouse binding not found")

        next_active = bool(payload.active) if payload.active is not None else bool(row["active"])

        sql_upd = text(
            """
            UPDATE shipping_provider_pricing_scheme_warehouses
               SET active = :active, updated_at = now()
             WHERE scheme_id = :sid AND warehouse_id = :wid
            """
        )
        db.execute(sql_upd, {"active": bool(next_active), "sid": int(scheme_id), "wid": int(warehouse_id)})
        db.commit()

        wh = WarehouseLiteOut(
            id=int(row["w_id"]),
            name=str(row["w_name"]),
            code=(str(row["w_code"]) if row["w_code"] is not None else None),
            active=bool(row["w_active"]),
        )
        out = SchemeWarehouseOut(
            scheme_id=int(row["scheme_id"]),
            warehouse_id=int(row["warehouse_id"]),
            active=bool(next_active),
            warehouse=wh,
        )
        return SchemeWarehousePatchOut(ok=True, data=out)

    @router.delete(
        "/pricing-schemes/{scheme_id}/warehouses/{warehouse_id}",
        response_model=SchemeWarehouseDeleteOut,
    )
    def delete_scheme_warehouse(
        scheme_id: int = Path(..., ge=1),
        warehouse_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ) -> SchemeWarehouseDeleteOut:
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        sql_del = text(
            """
            DELETE FROM shipping_provider_pricing_scheme_warehouses
             WHERE scheme_id = :sid AND warehouse_id = :wid
            """
        )
        res = db.execute(sql_del, {"sid": int(scheme_id), "wid": int(warehouse_id)})
        db.commit()

        # 不暴露 rowcount 语义给前端：只返回事实 key
        if getattr(res, "rowcount", 0) == 0:
            raise HTTPException(status_code=404, detail="Scheme warehouse binding not found")

        return SchemeWarehouseDeleteOut(
            ok=True,
            data={"scheme_id": int(scheme_id), "warehouse_id": int(warehouse_id)},
        )
