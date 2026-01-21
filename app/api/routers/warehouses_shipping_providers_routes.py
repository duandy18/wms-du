# app/api/routers/warehouses_shipping_providers_routes.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.warehouses_active_carriers_summary_schemas import (
    ActiveCarrierOut,
    WarehouseActiveCarriersOut,
    WarehouseActiveCarriersSummaryOut,
)
from app.api.routers.warehouses_helpers import check_perm
from app.api.routers.warehouses_shipping_providers_schemas import (
    ShippingProviderLiteOut,
    WarehouseShippingProviderBindIn,
    WarehouseShippingProviderBindOut,
    WarehouseShippingProviderDeleteOut,
    WarehouseShippingProviderListOut,
    WarehouseShippingProviderOut,
    WarehouseShippingProviderUpdateIn,
    WarehouseShippingProviderUpdateOut,
)
from app.db.deps import get_db


def _ensure_warehouse_exists_or_404(session: AsyncSession, warehouse_id: int) -> Any:
    sql = text("SELECT 1 FROM warehouses WHERE id = :wid LIMIT 1")
    return sql


def _row_to_out(row: Dict[str, Any]) -> WarehouseShippingProviderOut:
    return WarehouseShippingProviderOut(
        warehouse_id=int(row["warehouse_id"]),
        shipping_provider_id=int(row["shipping_provider_id"]),
        active=bool(row["wsp_active"]),
        priority=int(row["wsp_priority"]),
        pickup_cutoff_time=row.get("pickup_cutoff_time"),
        remark=row.get("remark"),
        provider=ShippingProviderLiteOut(
            id=int(row["provider_id"]),
            name=str(row["provider_name"]),
            code=row.get("provider_code"),
            active=bool(row["provider_active"]),
        ),
    )


def register(router: APIRouter) -> None:
    @router.get(
        "/warehouses/active-carriers/summary",
        response_model=WarehouseActiveCarriersSummaryOut,
    )
    async def list_warehouses_active_carriers_summary(
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseActiveCarriersSummaryOut:
        """
        Phase 2.1：后端汇总接口（消除 N+1）

        刚性契约口径：
        - 只返回正在服务的快递公司：wsp.active = true AND sp.active = true
        - 不做推荐策略，不做 fallback
        - 排序仅用于展示稳定：
          warehouse_id ASC, wsp.priority ASC, sp.priority ASC, sp.id ASC
        """
        check_perm(db, current_user, ["config.store.read"])

        sql = text(
            """
            SELECT
              wsp.warehouse_id,
              sp.id   AS provider_id,
              sp.code AS provider_code,
              sp.name AS provider_name,
              wsp.priority AS wsp_priority,
              sp.priority  AS sp_priority
            FROM warehouse_shipping_providers AS wsp
            JOIN shipping_providers AS sp
              ON sp.id = wsp.shipping_provider_id
            WHERE wsp.active = true
              AND sp.active = true
            ORDER BY wsp.warehouse_id ASC, wsp.priority ASC, sp.priority ASC, sp.id ASC
            """
        )

        rows = (await session.execute(sql)).mappings().all()

        by_wid: Dict[int, list[ActiveCarrierOut]] = {}
        for r in rows:
            wid = int(r["warehouse_id"])
            by_wid.setdefault(wid, []).append(
                ActiveCarrierOut(
                    provider_id=int(r["provider_id"]),
                    code=r.get("provider_code"),
                    name=str(r["provider_name"]),
                    priority=int(r.get("wsp_priority") or 0),
                )
            )

        data = [
            WarehouseActiveCarriersOut(
                warehouse_id=wid,
                active_carriers=carriers,
                active_carriers_count=len(carriers),
            )
            for wid, carriers in sorted(by_wid.items(), key=lambda x: x[0])
        ]

        return WarehouseActiveCarriersSummaryOut(ok=True, data=data)

    @router.get(
        "/warehouses/{warehouse_id}/shipping-providers",
        response_model=WarehouseShippingProviderListOut,
    )
    async def list_warehouse_shipping_providers(
        warehouse_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseShippingProviderListOut:
        check_perm(db, current_user, ["config.store.read"])

        # 404 if warehouse not exist
        chk = (await session.execute(text("SELECT 1 FROM warehouses WHERE id=:wid"), {"wid": warehouse_id})).first()
        if not chk:
            raise HTTPException(status_code=404, detail="warehouse not found")

        sql = text(
            """
            SELECT
              wsp.warehouse_id,
              wsp.shipping_provider_id,
              wsp.active AS wsp_active,
              wsp.priority AS wsp_priority,
              wsp.pickup_cutoff_time,
              wsp.remark,
              sp.id AS provider_id,
              sp.name AS provider_name,
              sp.code AS provider_code,
              sp.active AS provider_active
            FROM warehouse_shipping_providers AS wsp
            JOIN shipping_providers AS sp
              ON sp.id = wsp.shipping_provider_id
            WHERE wsp.warehouse_id = :wid
            ORDER BY wsp.priority ASC, wsp.id ASC
            """
        )

        rows = (await session.execute(sql, {"wid": warehouse_id})).mappings().all()
        data = [_row_to_out(dict(r)) for r in rows]
        return WarehouseShippingProviderListOut(ok=True, data=data)

    @router.post(
        "/warehouses/{warehouse_id}/shipping-providers/bind",
        status_code=status.HTTP_201_CREATED,
        response_model=WarehouseShippingProviderBindOut,
    )
    async def bind_shipping_provider_to_warehouse(
        warehouse_id: int = Path(..., ge=1),
        payload: WarehouseShippingProviderBindIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseShippingProviderBindOut:
        check_perm(db, current_user, ["config.store.write"])

        # warehouse exists
        chk = (await session.execute(text("SELECT 1 FROM warehouses WHERE id=:wid"), {"wid": warehouse_id})).first()
        if not chk:
            raise HTTPException(status_code=404, detail="warehouse not found")

        # provider exists
        prow = (
            await session.execute(
                text("SELECT id, name, code, active FROM shipping_providers WHERE id=:pid"),
                {"pid": int(payload.shipping_provider_id)},
            )
        ).mappings().first()
        if not prow:
            raise HTTPException(status_code=404, detail="shipping_provider not found")

        sql = text(
            """
            INSERT INTO warehouse_shipping_providers
              (warehouse_id, shipping_provider_id, active, priority, pickup_cutoff_time, remark)
            VALUES
              (:wid, :pid, :active, :priority, :cutoff, :remark)
            ON CONFLICT (warehouse_id, shipping_provider_id) DO NOTHING
            RETURNING
              warehouse_id, shipping_provider_id, active AS wsp_active, priority AS wsp_priority,
              pickup_cutoff_time, remark
            """
        )

        row = (
            await session.execute(
                sql,
                {
                    "wid": warehouse_id,
                    "pid": int(payload.shipping_provider_id),
                    "active": bool(payload.active),
                    "priority": int(payload.priority),
                    "cutoff": payload.pickup_cutoff_time,
                    "remark": payload.remark,
                },
            )
        ).mappings().first()

        if not row:
            # already exists
            raise HTTPException(status_code=409, detail="warehouse_shipping_provider already bound")

        await session.commit()

        out = _row_to_out(
            {
                **dict(row),
                "provider_id": prow["id"],
                "provider_name": prow["name"],
                "provider_code": prow.get("code"),
                "provider_active": prow["active"],
            }
        )
        return WarehouseShippingProviderBindOut(ok=True, data=out)

    @router.patch(
        "/warehouses/{warehouse_id}/shipping-providers/{shipping_provider_id}",
        response_model=WarehouseShippingProviderUpdateOut,
    )
    async def update_warehouse_shipping_provider(
        warehouse_id: int = Path(..., ge=1),
        shipping_provider_id: int = Path(..., ge=1),
        payload: WarehouseShippingProviderUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseShippingProviderUpdateOut:
        check_perm(db, current_user, ["config.store.write"])

        fields: Dict[str, Any] = {}
        if payload.active is not None:
            fields["active"] = payload.active
        if payload.priority is not None:
            fields["priority"] = payload.priority
        if payload.pickup_cutoff_time is not None:
            fields["pickup_cutoff_time"] = payload.pickup_cutoff_time
        if payload.remark is not None:
            fields["remark"] = payload.remark

        if not fields:
            raise HTTPException(status_code=400, detail="no fields to update")

        set_clauses = []
        params: Dict[str, Any] = {"wid": warehouse_id, "pid": shipping_provider_id}
        for idx, (k, v) in enumerate(fields.items()):
            pname = f"v{idx}"
            set_clauses.append(f"{k} = :{pname}")
            params[pname] = v

        sql = text(
            f"""
            UPDATE warehouse_shipping_providers
               SET {", ".join(set_clauses)}
             WHERE warehouse_id = :wid
               AND shipping_provider_id = :pid
            RETURNING
              warehouse_id, shipping_provider_id, active AS wsp_active, priority AS wsp_priority,
              pickup_cutoff_time, remark
            """
        )

        row = (await session.execute(sql, params)).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="warehouse_shipping_provider not found")

        prow = (
            await session.execute(
                text("SELECT id, name, code, active FROM shipping_providers WHERE id=:pid"),
                {"pid": shipping_provider_id},
            )
        ).mappings().first()
        if not prow:
            # 理论上不应发生（外键 RESTRICT），但仍给出明确错误
            raise HTTPException(status_code=404, detail="shipping_provider not found")

        await session.commit()

        out = _row_to_out(
            {
                **dict(row),
                "provider_id": prow["id"],
                "provider_name": prow["name"],
                "provider_code": prow.get("code"),
                "provider_active": prow["active"],
            }
        )
        return WarehouseShippingProviderUpdateOut(ok=True, data=out)

    @router.delete(
        "/warehouses/{warehouse_id}/shipping-providers/{shipping_provider_id}",
        response_model=WarehouseShippingProviderDeleteOut,
    )
    async def unbind_shipping_provider_from_warehouse(
        warehouse_id: int = Path(..., ge=1),
        shipping_provider_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseShippingProviderDeleteOut:
        check_perm(db, current_user, ["config.store.write"])

        sql = text(
            """
            DELETE FROM warehouse_shipping_providers
             WHERE warehouse_id = :wid
               AND shipping_provider_id = :pid
            RETURNING warehouse_id, shipping_provider_id
            """
        )

        row = (await session.execute(sql, {"wid": warehouse_id, "pid": shipping_provider_id})).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="warehouse_shipping_provider not found")

        await session.commit()
        return WarehouseShippingProviderDeleteOut(
            ok=True,
            data={"warehouse_id": int(row["warehouse_id"]), "shipping_provider_id": int(row["shipping_provider_id"])},
        )
