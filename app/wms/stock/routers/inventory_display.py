from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.stock.contracts.inventory_display import (
    InventoryDisplayResponse,
    ItemDetailDisplayResponse,
)
from app.wms.stock.services.inventory_display import query_inventory_display_paged
from app.wms.stock.services.item_detail_display import query_item_detail_display

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/inventory", response_model=InventoryDisplayResponse)
async def inventory_display(
    q: str | None = Query(None, description="模糊搜索 items.name / items.sku"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    库存总览展示接口（实时视图）。
    """
    return await query_inventory_display_paged(
        session=session,
        q=q,
        offset=offset,
        limit=limit,
    )


@router.get("/item-detail/{item_id}", response_model=ItemDetailDisplayResponse)
async def item_detail_display(
    item_id: int,
    pools: str = Query(
        "MAIN",
        description="逗号分隔的库存池（预留参数，目前仅 MAIN 有效）",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    单品仓+批次明细展示接口。
    """
    pool_list = [p.strip().upper() for p in pools.split(",") if p.strip()] or ["MAIN"]

    return await query_item_detail_display(
        session=session,
        item_id=item_id,
        pools=pool_list,
    )
