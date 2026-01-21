# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_warehouses.py
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme_warehouses_schemas import (
    SchemeWarehouseOut,
    SchemeWarehousesGetOut,
    SchemeWarehousesPutIn,
    SchemeWarehousesPutOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def _dedup_ints(xs: List[int]) -> List[int]:
    seen = set()
    out: List[int] = []
    for x in xs:
        xi = int(x)
        if xi <= 0:
            continue
        if xi in seen:
            continue
        seen.add(xi)
        out.append(xi)
    return out


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

        sql = text(
            """
            SELECT warehouse_id, active
              FROM shipping_provider_pricing_scheme_warehouses
             WHERE scheme_id = :sid
             ORDER BY warehouse_id ASC
            """
        )
        rows = db.execute(sql, {"sid": int(scheme_id)}).mappings().all()
        data = [SchemeWarehouseOut(warehouse_id=int(r["warehouse_id"]), active=bool(r["active"])) for r in rows]
        return SchemeWarehousesGetOut(ok=True, data=data)

    @router.put(
        "/pricing-schemes/{scheme_id}/warehouses",
        response_model=SchemeWarehousesPutOut,
    )
    def put_scheme_warehouses(
        scheme_id: int = Path(..., ge=1),
        payload: SchemeWarehousesPutIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ) -> SchemeWarehousesPutOut:
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        # 1) 规范化 + 去重
        ids = _dedup_ints(payload.warehouse_ids)

        # 2) 校验 warehouses 存在（允许空列表：表示“无适用仓”）
        if ids:
            sql_chk = text("SELECT id FROM warehouses WHERE id = ANY(:ids)")
            rows = db.execute(sql_chk, {"ids": ids}).mappings().all()
            exists = {int(r["id"]) for r in rows}
            missing = [x for x in ids if x not in exists]
            if missing:
                raise HTTPException(status_code=404, detail=f"Warehouse not found: {missing}")

        # 3) 全量替换（delete + insert）
        db.execute(
            text("DELETE FROM shipping_provider_pricing_scheme_warehouses WHERE scheme_id = :sid"),
            {"sid": int(scheme_id)},
        )

        if ids:
            # 批量插入：用 VALUES 列表（最兼容），避免 executemany 风格差异
            params: Dict[str, object] = {"sid": int(scheme_id), "active": bool(payload.active)}
            values_sql_parts: List[str] = []
            for i, wid in enumerate(ids):
                k = f"wid{i}"
                params[k] = int(wid)
                values_sql_parts.append(f"(:sid, :{k}, :active)")

            sql_ins = text(
                f"""
                INSERT INTO shipping_provider_pricing_scheme_warehouses
                  (scheme_id, warehouse_id, active)
                VALUES
                  {", ".join(values_sql_parts)}
                """
            )
            db.execute(sql_ins, params)

        db.commit()

        data = [SchemeWarehouseOut(warehouse_id=int(wid), active=bool(payload.active)) for wid in ids]
        return SchemeWarehousesPutOut(ok=True, data=data)
