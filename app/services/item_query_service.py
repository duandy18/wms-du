# app/services/item_query_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.item import Item
from app.services.item_repo import get_item_by_id as repo_get_item_by_id
from app.services.item_repo import get_item_by_sku as repo_get_item_by_sku
from app.services.item_repo import get_items as repo_get_items


class ItemQueryService:
    """
    查询层（Query）：

    - 只负责从 repo 取数据
    - 不负责 decorate / barcode / test-set 投影
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_items(
        self,
        *,
        supplier_id: Optional[int] = None,
        enabled: Optional[bool] = None,
        q: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Item]:
        return repo_get_items(self.db, supplier_id=supplier_id, enabled=enabled, q=q, limit=limit)

    def get_item_by_id(self, id: int) -> Item | None:
        return repo_get_item_by_id(self.db, id)

    def get_item_by_sku(self, sku: str) -> Item | None:
        return repo_get_item_by_sku(self.db, sku)
