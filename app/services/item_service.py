# app/services/item_service.py
from __future__ import annotations

from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.item import Item


class ItemService:
    """最小可用 Item 领域服务（同步 Session 版）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # 创建物料（SKU 唯一）
    def create_item(self, sku: str, name: str, description: Optional[str] = None) -> Item:
        sku = (sku or "").strip()
        name = (name or "").strip()
        if not sku or not name:
            raise ValueError("SKU and name are required")

        # 已存在直接抛错（也可改成返回已存在对象）
        exists = self.db.execute(select(Item).where(Item.sku == sku)).scalar_one_or_none()
        if exists:
            raise ValueError(f"Item with sku '{sku}' already exists")

        obj = Item(sku=sku, name=name, description=description or "")
        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError("SKU duplicate") from e
        self.db.refresh(obj)
        return obj

    # 查询全部物料
    def get_all_items(self) -> List[Item]:
        rows = self.db.execute(select(Item).order_by(Item.id.asc())).scalars().all()
        return list(rows)

    # 通过 SKU 查询单个物料
    def get_item_by_sku(self, sku: str) -> Optional[Item]:
        return self.db.execute(select(Item).where(Item.sku == sku)).scalar_one_or_none()
