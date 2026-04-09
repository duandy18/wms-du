# app/pms/public/items/routers/items_read.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.public.items.contracts.item_basic import ItemBasic
from app.pms.public.items.contracts.item_query import ItemReadQuery
from app.pms.public.items.services.item_read_service import ItemReadService

router = APIRouter(prefix="/public/items", tags=["pms-public-items"])


def get_item_read_service(db: Session = Depends(get_db)) -> ItemReadService:
    return ItemReadService(db)


@router.get("", response_model=list[ItemBasic], status_code=status.HTTP_200_OK)
def list_public_items(
    supplier_id: Optional[int] = Query(None, ge=1, description="按供应商过滤"),
    enabled: Optional[bool] = Query(None, description="按启用状态过滤"),
    q: Optional[str] = Query(None, description="关键词搜索（sku/name）"),
    limit: Optional[int] = Query(None, ge=1, le=200, description="限制返回条数（默认 50，最大 200）"),
    service: ItemReadService = Depends(get_item_read_service),
) -> list[ItemBasic]:
    query = ItemReadQuery(
        supplier_id=supplier_id,
        enabled=enabled,
        q=q,
        limit=limit,
    )
    return service.list_basic(query=query)


@router.get("/{item_id}", response_model=ItemBasic, status_code=status.HTTP_200_OK)
def get_public_item_by_id(
    item_id: int,
    service: ItemReadService = Depends(get_item_read_service),
) -> ItemBasic:
    obj = service.get_basic_by_id(item_id=int(item_id))
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj
