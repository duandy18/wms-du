# app/api/routers/warehouses_shipping_providers_routes_bindings.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.warehouses_helpers import check_perm
from app.api.routers.warehouses_shipping_providers_helpers import LIST_SQL, row_to_out
from app.api.routers.warehouses_shipping_providers_schemas import (
    WarehouseShippingProviderBindIn,
    WarehouseShippingProviderBindOut,
    WarehouseShippingProviderBulkUpsertIn,
    WarehouseShippingProviderBulkUpsertOut,
    WarehouseShippingProviderDeleteOut,
    WarehouseShippingProviderListOut,
    WarehouseShippingProviderUpdateIn,
    WarehouseShippingProviderUpdateOut,
)
from app.db.deps import get_db


def register(router: APIRouter) -> None:
    @router.get(
        "/warehouses/{warehouse_id}/shipping-providers",
        response_model=WarehouseShippingProviderListOut,
    )
    async def list_warehouse_shipping_providers(
        warehouse_id: int = Path(..., ge=1),
        session=Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseShippingProviderListOut:
        check_perm(db, current_user, ["config.store.read"])

        chk = (await session.execute(text("SELECT 1 FROM warehouses WHERE id=:wid"), {"wid": warehouse_id})).first()
        if not chk:
            raise HTTPException(status_code=404, detail="warehouse not found")

        rows = (await session.execute(LIST_SQL, {"wid": warehouse_id})).mappings().all()
        data = [row_to_out(dict(r)) for r in rows]
        return WarehouseShippingProviderListOut(ok=True, data=data)

    @router.post(
        "/warehouses/{warehouse_id}/shipping-providers/bind",
        status_code=status.HTTP_201_CREATED,
        response_model=WarehouseShippingProviderBindOut,
    )
    async def bind_shipping_provider_to_warehouse(
        warehouse_id: int = Path(..., ge=1),
        payload: WarehouseShippingProviderBindIn = ...,
        session=Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseShippingProviderBindOut:
        check_perm(db, current_user, ["config.store.write"])

        chk = (await session.execute(text("SELECT 1 FROM warehouses WHERE id=:wid"), {"wid": warehouse_id})).first()
        if not chk:
            raise HTTPException(status_code=404, detail="warehouse not found")

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
            raise HTTPException(status_code=409, detail="warehouse_shipping_provider already bound")

        await session.commit()

        out = row_to_out(
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
        session=Depends(get_session),
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
            raise HTTPException(status_code=404, detail="shipping_provider not found")

        await session.commit()

        out = row_to_out(
            {
                **dict(row),
                "provider_id": prow["id"],
                "provider_name": prow["name"],
                "provider_code": prow.get("code"),
                "provider_active": prow["active"],
            }
        )
        return WarehouseShippingProviderUpdateOut(ok=True, data=out)

    @router.put(
        "/warehouses/{warehouse_id}/shipping-providers",
        response_model=WarehouseShippingProviderBulkUpsertOut,
    )
    async def bulk_upsert_warehouse_shipping_providers(
        warehouse_id: int = Path(..., ge=1),
        payload: WarehouseShippingProviderBulkUpsertIn = ...,
        session=Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseShippingProviderBulkUpsertOut:
        check_perm(db, current_user, ["config.store.write"])

        chk = (await session.execute(text("SELECT 1 FROM warehouses WHERE id=:wid"), {"wid": warehouse_id})).first()
        if not chk:
            raise HTTPException(status_code=404, detail="warehouse not found")

        items = payload.items or []
        pids = [int(it.shipping_provider_id) for it in items]

        if pids:
            rows = (
                await session.execute(
                    text("SELECT id FROM shipping_providers WHERE id = ANY(:pids)"),
                    {"pids": pids},
                )
            ).mappings().all()
            exist_ids = {int(r["id"]) for r in rows}
            missing = [pid for pid in pids if pid not in exist_ids]
            if missing:
                raise HTTPException(status_code=404, detail="shipping_provider not found")

        upsert_sql = text(
            """
            INSERT INTO warehouse_shipping_providers
              (warehouse_id, shipping_provider_id, active, priority, pickup_cutoff_time, remark)
            VALUES
              (:wid, :pid, :active, :priority, :cutoff, :remark)
            ON CONFLICT (warehouse_id, shipping_provider_id) DO UPDATE SET
              active = EXCLUDED.active,
              priority = EXCLUDED.priority,
              pickup_cutoff_time = EXCLUDED.pickup_cutoff_time,
              remark = EXCLUDED.remark
            """
        )

        for it in items:
            await session.execute(
                upsert_sql,
                {
                    "wid": warehouse_id,
                    "pid": int(it.shipping_provider_id),
                    "active": bool(it.active),
                    "priority": int(it.priority),
                    "cutoff": it.pickup_cutoff_time,
                    "remark": it.remark,
                },
            )

        if payload.disable_missing:
            if pids:
                await session.execute(
                    text(
                        """
                        UPDATE warehouse_shipping_providers
                           SET active = false
                         WHERE warehouse_id = :wid
                           AND NOT (shipping_provider_id = ANY(:pids))
                        """
                    ),
                    {"wid": warehouse_id, "pids": pids},
                )
            else:
                await session.execute(
                    text(
                        """
                        UPDATE warehouse_shipping_providers
                           SET active = false
                         WHERE warehouse_id = :wid
                        """
                    ),
                    {"wid": warehouse_id},
                )

        await session.commit()

        rows = (await session.execute(LIST_SQL, {"wid": warehouse_id})).mappings().all()
        data = [row_to_out(dict(r)) for r in rows]
        return WarehouseShippingProviderBulkUpsertOut(ok=True, data=data)

    @router.delete(
        "/warehouses/{warehouse_id}/shipping-providers/{shipping_provider_id}",
        response_model=WarehouseShippingProviderDeleteOut,
    )
    async def unbind_shipping_provider_from_warehouse(
        warehouse_id: int = Path(..., ge=1),
        shipping_provider_id: int = Path(..., ge=1),
        session=Depends(get_session),
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
