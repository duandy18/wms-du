from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.snapshot_api import ItemDetailResponse
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


@router.get("/inventory")
async def inventory_snapshot(
    q: str | None = Query(None, description="模糊搜索 items.name / items.sku"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    SnapshotPage 主列表接口（库存总览，实时视图）。

    返回结构：
    {
      "total": int,
      "offset": int,
      "limit": int,
      "rows": [
        {
          "item_id": int,
          "item_name": str,
          "total_qty": int,
          "top2_locations": [
            { "warehouse_id": int, "batch_code": str, "qty": int },
            ...
          ],
          "earliest_expiry": "YYYY-MM-DD" | null,
          "near_expiry": bool
        }
      ]
    }
    """
    return await SnapshotService.query_inventory_snapshot_paged(
        session=session,
        q=q,
        offset=offset,
        limit=limit,
    )


@router.get("/item-detail/{item_id}", response_model=ItemDetailResponse)
async def item_detail(
    item_id: int,
    pools: str = Query(
        "MAIN",
        description="逗号分隔的库存池（预留参数，目前仅 MAIN 有效）",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    Drawer V2 使用的“单品仓+批次明细”接口。
    """
    pool_list = [p.strip().upper() for p in pools.split(",") if p.strip()] or ["MAIN"]

    return await SnapshotService.query_item_detail(
        session=session,
        item_id=item_id,
        pools=pool_list,
    )
