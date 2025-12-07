# app/services/item_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.item import Item


class ItemService:
    """Item 领域服务（同步 Session 版）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -----------------------------
    # 1) 按 SKU 创建商品
    # -----------------------------
    def create_item(
        self,
        *,
        sku: str,
        name: str,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        enabled: bool = True,
        supplier_id: Optional[int] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,  # ⭐ 新增
    ) -> Item:
        sku = (sku or "").strip()
        name = (name or "").strip()
        spec_val = spec.strip() if isinstance(spec, str) else None
        unit_val = (uom or "PCS").strip().upper() or "PCS"

        if not sku or not name:
            raise ValueError("SKU and name are required")

        exists = self.db.execute(select(Item).where(Item.sku == sku)).scalar_one_or_none()
        if exists:
            raise ValueError("SKU duplicate")

        obj = Item(
            sku=sku,
            name=name,
            unit=unit_val,
            spec=spec_val,
            enabled=bool(enabled),
            supplier_id=supplier_id,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,  # ⭐ 新增
        )

        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "items_sku_key" in raw or ("unique" in raw and "sku" in raw):
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return obj

    # -----------------------------
    # 2) 按 ID 创建商品（幂等）
    # -----------------------------
    def create_item_by_id(
        self,
        *,
        id: int,
        sku: Optional[str] = None,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        enabled: Optional[bool] = True,
        supplier_id: Optional[int] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,  # ⭐ 新增
    ) -> Item:
        if not id or id <= 0:
            raise ValueError("id 必须为正整数")

        exists = self.db.get(Item, id)
        if exists is not None:
            return exists

        sku_val = (sku or str(id)).strip()
        name_val = (name or f"ITEM-{id}").strip()
        spec_val = spec.strip() if isinstance(spec, str) else None
        unit_val = (uom or "PCS").strip().upper() or "PCS"
        enabled_val = True if enabled is None else bool(enabled)

        obj = Item(
            id=id,
            sku=sku_val,
            name=name_val,
            unit=unit_val,
            spec=spec_val,
            enabled=enabled_val,
            supplier_id=supplier_id,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,  # ⭐ 新增
        )

        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "items_pkey" in raw:
                raise ValueError(f"Item id {id} already exists") from e
            if "items_sku_key" in raw:
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return obj

    # -----------------------------
    # 3) 查询
    # -----------------------------
    def get_all_items(self) -> List[Item]:
        rows = self.db.execute(select(Item).order_by(Item.id.asc())).scalars().all()
        return list(rows)

    def get_item_by_id(self, id: int) -> Optional[Item]:
        if not id or id <= 0:
            return None
        return self.db.get(Item, id)

    def get_item_by_sku(self, sku: str) -> Optional[Item]:
        sku = (sku or "").strip()
        if not sku:
            return None
        return self.db.execute(select(Item).where(Item.sku == sku)).scalar_one_or_none()

    # -----------------------------
    # 4) 更新
    # -----------------------------
    def update_item(
        self,
        *,
        id: int,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        enabled: Optional[bool] = None,
        supplier_id: Optional[int] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,  # ⭐ 新增
    ) -> Item:
        obj = self.db.get(Item, id)
        if obj is None:
            raise ValueError("Item not found")

        changed = False

        if name is not None:
            new_name = name.strip()
            if not new_name:
                raise ValueError("name 不能为空")
            obj.name = new_name
            changed = True

        if spec is not None:
            obj.spec = spec.strip() if isinstance(spec, str) else None
            changed = True

        if uom is not None:
            unit_val = (uom or "PCS").strip().upper() or "PCS"
            obj.unit = unit_val
            changed = True

        if enabled is not None:
            obj.enabled = bool(enabled)
            changed = True

        if supplier_id is not None:
            obj.supplier_id = supplier_id
            changed = True

        if shelf_life_value is not None:
            obj.shelf_life_value = shelf_life_value
            changed = True

        if shelf_life_unit is not None:
            obj.shelf_life_unit = shelf_life_unit
            changed = True

        if weight_kg is not None:
            obj.weight_kg = weight_kg
            changed = True

        if not changed:
            return obj

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return obj
