# app/shipping_assist/pricing/bindings/read_routes.py
#
# 分拆说明：
# - 本文件从原 routes.py 中拆出 bindings 读接口。
# - 当前只负责：
#   1) 查询仓库 bindings 列表
#   2) 查询某 binding 的可挂载模板候选
#   3) 提供读侧复用辅助函数 _load_binding_row_or_404
# - 维护约束：
#   - 不放写接口
#   - 不放运行控制接口
#   - 写接口与运行控制接口需要复用读辅助时，从本文件导入

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.shipping_assist.permissions import check_config_perm
from app.shipping_assist.pricing.bindings.contracts import (
    WarehouseShippingProviderListOut,
)
from app.shipping_assist.pricing.bindings.helpers import LIST_SQL, row_to_out
from app.shipping_assist.pricing.templates.repository import (
    list_bindable_templates,
)
from app.shipping_assist.pricing.templates.contracts.template import TemplateListOut

router = APIRouter()


async def _load_binding_row_or_404(
    session: AsyncSession,
    *,
    warehouse_id: int,
    shipping_provider_id: int,
) -> Dict[str, Any]:
    rows = (await session.execute(LIST_SQL, {"wid": warehouse_id})).mappings().all()
    for row in rows:
        if int(row["shipping_provider_id"]) == int(shipping_provider_id):
            return dict(row)
    raise HTTPException(status_code=404, detail="warehouse_shipping_provider not found")


@router.get(
    "/warehouses/{warehouse_id}/bindings",
    response_model=WarehouseShippingProviderListOut,
    name="pricing_list_warehouse_bindings",
)
async def pricing_list_warehouse_bindings(
    warehouse_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseShippingProviderListOut:
    check_config_perm(db, current_user, ["config.store.read"])

    chk = (
        await session.execute(
            text("SELECT 1 FROM warehouses WHERE id=:wid"),
            {"wid": warehouse_id},
        )
    ).first()
    if not chk:
        raise HTTPException(status_code=404, detail="warehouse not found")

    rows = (await session.execute(LIST_SQL, {"wid": warehouse_id})).mappings().all()
    data = [row_to_out(dict(r)) for r in rows]
    return WarehouseShippingProviderListOut(ok=True, data=data)


@router.get(
    "/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/template-candidates",
    response_model=TemplateListOut,
    name="pricing_binding_template_candidates",
)
async def pricing_binding_template_candidates(
    warehouse_id: int = Path(..., ge=1),
    shipping_provider_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TemplateListOut:
    check_config_perm(db, current_user, ["config.store.read"])

    warehouse_chk = (
        await session.execute(
            text("SELECT 1 FROM warehouses WHERE id=:wid"),
            {"wid": warehouse_id},
        )
    ).first()
    if not warehouse_chk:
        raise HTTPException(status_code=404, detail="warehouse not found")

    provider_chk = (
        await session.execute(
            text("SELECT 1 FROM shipping_providers WHERE id=:pid"),
            {"pid": int(shipping_provider_id)},
        )
    ).first()
    if not provider_chk:
        raise HTTPException(status_code=404, detail="shipping_provider not found")

    data = list_bindable_templates(
        db,
        shipping_provider_id=int(shipping_provider_id),
    )
    return TemplateListOut(ok=True, data=data)
