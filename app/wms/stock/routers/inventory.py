from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.stock.contracts.inventory import (
    InventoryDetailQuery,
    InventoryDetailResponse,
    InventoryQuery,
    InventoryResponse,
)
from app.wms.stock.contracts.options import (
    InventoryOptionsQuery,
    InventoryOptionsResponse,
)
from app.wms.stock.services.inventory_options_service import InventoryOptionsService
from app.wms.stock.services.inventory_read_service import InventoryReadService

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/inventory", response_model=InventoryResponse)
async def list_inventory(
    q: str | None = Query(None, description="按商品编码/名称模糊搜索"),
    item_id: int | None = Query(None, ge=1, description="商品 ID"),
    warehouse_id: int | None = Query(None, ge=1, description="仓库 ID"),
    lot_code: str | None = Query(None, description="Lot 展示码"),
    near_expiry: bool | None = Query(None, description="是否只看临期"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> InventoryResponse:
    query = InventoryQuery(
        q=q,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=lot_code,
        near_expiry=near_expiry,
        offset=offset,
        limit=limit,
    )
    return await InventoryReadService.list_inventory(session, query=query)


@router.get("/inventory/{item_id}/detail", response_model=InventoryDetailResponse)
async def get_inventory_detail(
    item_id: int = Path(..., ge=1),
    warehouse_id: int | None = Query(None, ge=1, description="仓库 ID（可选）"),
    lot_code: str | None = Query(None, description="Lot 展示码（可选）"),
    pools: str = Query("MAIN", description="逗号分隔库存池；当前仅 MAIN 有效"),
    session: AsyncSession = Depends(get_session),
) -> InventoryDetailResponse:
    pool_list = [p.strip().upper() for p in pools.split(",") if p.strip()] or ["MAIN"]
    query = InventoryDetailQuery(
        warehouse_id=warehouse_id,
        lot_code=lot_code,
        pools=pool_list,
    )
    return await InventoryReadService.get_inventory_detail(
        session,
        item_id=item_id,
        query=query,
    )


@router.get("/options", response_model=InventoryOptionsResponse)
async def get_inventory_options(
    item_q: str | None = Query(None, description="商品编码/名称模糊搜索"),
    item_limit: int = Query(200, ge=1, le=500, description="商品选项最大返回数"),
    warehouses_active_only: bool = Query(True, description="是否只返回启用仓库"),
    session: AsyncSession = Depends(get_session),
) -> InventoryOptionsResponse:
    query = InventoryOptionsQuery(
        item_q=item_q,
        item_limit=item_limit,
        warehouses_active_only=warehouses_active_only,
    )
    return await InventoryOptionsService.get_options(session, query=query)


__all__ = ["router"]
