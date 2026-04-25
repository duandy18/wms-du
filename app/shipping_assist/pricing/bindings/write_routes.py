# app/shipping_assist/pricing/bindings/write_routes.py
#
# 分拆说明：
# - 本文件从原 routes.py 中拆出 bindings 配置写接口。
# - 当前只负责：
#   1) bind
#   2) update（绑定配置更新）
#   3) bulk upsert
#   4) delete / unbind
# - 维护约束：
#   - 本文件属于“配置层”，不是“运行控制层”
#   - 模板唯一性校验统一走 _ensure_binding_template_allowed

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.shipping_assist.permissions import check_config_perm
from app.shipping_assist.pricing.bindings.contracts import (
    WarehouseShippingProviderBindIn,
    WarehouseShippingProviderBindOut,
    WarehouseShippingProviderBulkUpsertIn,
    WarehouseShippingProviderBulkUpsertOut,
    WarehouseShippingProviderDeleteOut,
    WarehouseShippingProviderUpdateIn,
    WarehouseShippingProviderUpdateOut,
)
from app.shipping_assist.pricing.bindings.helpers import LIST_SQL, row_to_out
from app.shipping_assist.pricing.bindings.read_routes import _load_binding_row_or_404
from app.shipping_assist.pricing.bindings.validators import (
    _ensure_binding_template_allowed,
)

router = APIRouter()


@router.post(
    "/warehouses/{warehouse_id}/bindings",
    status_code=status.HTTP_201_CREATED,
    response_model=WarehouseShippingProviderBindOut,
    name="pricing_bind_provider_to_warehouse",
)
async def pricing_bind_provider_to_warehouse(
    warehouse_id: int = Path(..., ge=1),
    payload: WarehouseShippingProviderBindIn = ...,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseShippingProviderBindOut:
    check_config_perm(db, current_user, ["config.store.write"])

    chk = (
        await session.execute(
            text("SELECT 1 FROM warehouses WHERE id=:wid"),
            {"wid": warehouse_id},
        )
    ).first()
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

    await _ensure_binding_template_allowed(
        session,
        db,
        shipping_provider_id=int(payload.shipping_provider_id),
        active_template_id=payload.active_template_id,
    )

    sql = text(
        """
        INSERT INTO warehouse_shipping_providers
          (
            warehouse_id,
            shipping_provider_id,
            active_template_id,
            active,
            priority,
            pickup_cutoff_time,
            remark
          )
        VALUES
          (
            :wid,
            :pid,
            :active_template_id,
            :active,
            :priority,
            :cutoff,
            :remark
          )
        ON CONFLICT (warehouse_id, shipping_provider_id) DO NOTHING
        RETURNING
          warehouse_id,
          shipping_provider_id,
          active_template_id,
          active AS wsp_active,
          priority AS wsp_priority,
          pickup_cutoff_time,
          remark
        """
    )

    row = (
        await session.execute(
            sql,
            {
                "wid": warehouse_id,
                "pid": int(payload.shipping_provider_id),
                "active_template_id": payload.active_template_id,
                "active": bool(payload.active),
                "priority": int(payload.priority),
                "cutoff": payload.pickup_cutoff_time,
                "remark": payload.remark,
            },
        )
    ).mappings().first()

    if not row:
        raise HTTPException(
            status_code=409,
            detail="warehouse_shipping_provider already bound",
        )

    await session.commit()

    binding_row = await _load_binding_row_or_404(
        session,
        warehouse_id=warehouse_id,
        shipping_provider_id=int(payload.shipping_provider_id),
    )
    return WarehouseShippingProviderBindOut(ok=True, data=row_to_out(binding_row))


@router.patch(
    "/warehouses/{warehouse_id}/bindings/{shipping_provider_id}",
    response_model=WarehouseShippingProviderUpdateOut,
    name="pricing_update_warehouse_binding",
)
async def pricing_update_warehouse_binding(
    warehouse_id: int = Path(..., ge=1),
    shipping_provider_id: int = Path(..., ge=1),
    payload: WarehouseShippingProviderUpdateIn = ...,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseShippingProviderUpdateOut:
    check_config_perm(db, current_user, ["config.store.write"])

    fields: Dict[str, Any] = {}
    if payload.active is not None:
        fields["active"] = payload.active
    if payload.priority is not None:
        fields["priority"] = payload.priority
    if payload.pickup_cutoff_time is not None:
        fields["pickup_cutoff_time"] = payload.pickup_cutoff_time
    if payload.remark is not None:
        fields["remark"] = payload.remark
    if payload.active_template_id is not None:
        await _ensure_binding_template_allowed(
            session,
            db,
            shipping_provider_id=shipping_provider_id,
            active_template_id=payload.active_template_id,
        )
        fields["active_template_id"] = payload.active_template_id

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
          warehouse_id,
          shipping_provider_id,
          active_template_id,
          active AS wsp_active,
          priority AS wsp_priority,
          pickup_cutoff_time,
          remark
        """
    )

    row = (await session.execute(sql, params)).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="warehouse_shipping_provider not found")

    await session.commit()

    binding_row = await _load_binding_row_or_404(
        session,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
    )
    return WarehouseShippingProviderUpdateOut(ok=True, data=row_to_out(binding_row))


@router.put(
    "/warehouses/{warehouse_id}/bindings",
    response_model=WarehouseShippingProviderBulkUpsertOut,
    name="pricing_bulk_upsert_warehouse_bindings",
)
async def pricing_bulk_upsert_warehouse_bindings(
    warehouse_id: int = Path(..., ge=1),
    payload: WarehouseShippingProviderBulkUpsertIn = ...,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseShippingProviderBulkUpsertOut:
    check_config_perm(db, current_user, ["config.store.write"])

    chk = (
        await session.execute(
            text("SELECT 1 FROM warehouses WHERE id=:wid"),
            {"wid": warehouse_id},
        )
    ).first()
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

    for it in items:
        await _ensure_binding_template_allowed(
            session,
            db,
            shipping_provider_id=int(it.shipping_provider_id),
            active_template_id=it.active_template_id,
        )

    upsert_sql = text(
        """
        INSERT INTO warehouse_shipping_providers
          (
            warehouse_id,
            shipping_provider_id,
            active_template_id,
            active,
            priority,
            pickup_cutoff_time,
            remark
          )
        VALUES
          (
            :wid,
            :pid,
            :active_template_id,
            :active,
            :priority,
            :cutoff,
            :remark
          )
        ON CONFLICT (warehouse_id, shipping_provider_id) DO UPDATE SET
          active_template_id = EXCLUDED.active_template_id,
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
                "active_template_id": it.active_template_id,
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
    "/warehouses/{warehouse_id}/bindings/{shipping_provider_id}",
    response_model=WarehouseShippingProviderDeleteOut,
    name="pricing_unbind_provider_from_warehouse",
)
async def pricing_unbind_provider_from_warehouse(
    warehouse_id: int = Path(..., ge=1),
    shipping_provider_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseShippingProviderDeleteOut:
    check_config_perm(db, current_user, ["config.store.write"])

    sql = text(
        """
        DELETE FROM warehouse_shipping_providers
         WHERE warehouse_id = :wid
           AND shipping_provider_id = :pid
        RETURNING warehouse_id, shipping_provider_id
        """
    )

    row = (
        await session.execute(
            sql,
            {"wid": warehouse_id, "pid": shipping_provider_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="warehouse_shipping_provider not found")

    await session.commit()
    return WarehouseShippingProviderDeleteOut(
        ok=True,
        data={
            "warehouse_id": int(row["warehouse_id"]),
            "shipping_provider_id": int(row["shipping_provider_id"]),
        },
    )
