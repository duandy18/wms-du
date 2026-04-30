# app/pms/items/routers/item_list.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.items.contracts.item_list import ItemListDetailOut, ItemListRowOut
from app.pms.items.services.item_list_service import ItemListReadService

router = APIRouter(prefix="/items", tags=["items-list"])


def get_item_list_read_service(db: Session = Depends(get_db)) -> ItemListReadService:
    return ItemListReadService(db)


@router.get("/list-rows", response_model=list[ItemListRowOut])
def list_item_rows(
    enabled: Optional[bool] = Query(None, description="true=有效商品；false=无效商品；不传=全部"),
    supplier_id: Optional[int] = Query(None, ge=1, description="按供应商过滤"),
    q: Optional[str] = Query(None, description="关键词搜索 SKU / 名称 / 规格 / 品牌 / 分类 / 供应商 / 主条码"),
    limit: int = Query(200, ge=1, le=500),
    service: ItemListReadService = Depends(get_item_list_read_service),
) -> list[ItemListRowOut]:
    return service.list_rows(
        enabled=enabled,
        supplier_id=supplier_id,
        q=q,
        limit=limit,
    )


@router.get("/{item_id}/list-detail", response_model=ItemListDetailOut)
def get_item_list_detail(
    item_id: int,
    service: ItemListReadService = Depends(get_item_list_read_service),
) -> ItemListDetailOut:
    detail = service.get_detail(item_id=int(item_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return detail
