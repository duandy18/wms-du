# app/pms/items/services/item_list_service.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.pms.items.contracts.item_list import ItemListRowOut
from app.pms.items.repos.item_list_repo import list_item_list_row_mappings


class ItemListReadService:
    """
    PMS 商品列表页 owner 读服务。

    只负责商品列表页的完整摘要行，不承载写入语义。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_rows(
        self,
        *,
        enabled: Optional[bool] = None,
        supplier_id: Optional[int] = None,
        q: Optional[str] = None,
        limit: int = 200,
    ) -> list[ItemListRowOut]:
        rows = list_item_list_row_mappings(
            self.db,
            enabled=enabled,
            supplier_id=supplier_id,
            q=q,
            limit=limit,
        )
        return [ItemListRowOut.model_validate(dict(row)) for row in rows]
