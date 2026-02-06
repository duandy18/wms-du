# app/services/item_service.py
from __future__ import annotations

import os
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.item import Item
from app.services.item_repo import get_item_by_id as repo_get_item_by_id
from app.services.item_repo import get_item_by_sku as repo_get_item_by_sku
from app.services.item_repo import get_items as repo_get_items
from app.services.item_rules import decorate_rules
from app.services.item_sku import next_sku


def _allow_create_item_by_id() -> bool:
    """
    “例外通道”总开关（默认关闭）：
    - 仅用于历史兼容/修复/运维脚本
    - 生产环境默认不应开启
    """
    return os.getenv("WMS_ALLOW_CREATE_ITEM_BY_ID", "").strip() == "1"


class ItemService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # 兼容 router：/items/sku/next
    def next_sku(self) -> str:
        return next_sku(self.db)

    def create_item(
        self,
        *,
        name: str,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        barcode: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        enabled: bool = True,
        supplier_id: Optional[int] = None,
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
    ) -> Item:
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")

        spec_val = spec.strip() if isinstance(spec, str) else None
        unit_val = (uom or "PCS").strip().upper() or "PCS"

        brand_val = brand.strip() if isinstance(brand, str) and brand.strip() else None
        category_val = category.strip() if isinstance(category, str) and category.strip() else None

        sku_val = self.next_sku()

        obj = Item(
            sku=sku_val,
            name=name,
            unit=unit_val,
            spec=spec_val,
            enabled=bool(enabled),
            supplier_id=supplier_id,
            brand=brand_val,
            category=category_val,
            has_shelf_life=bool(has_shelf_life) if has_shelf_life is not None else False,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
        )

        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "items_sku_key" in raw or ("unique" in raw and "sku" in raw):
                # 理论上不会发生（sequence 保证唯一），但保留防御
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return decorate_rules(obj)

    def create_item_by_id(
        self,
        *,
        id: int,
        sku: Optional[str] = None,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        barcode: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        enabled: Optional[bool] = True,
        supplier_id: Optional[int] = None,
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
    ) -> Item:
        """
        🚫 例外通道（默认关闭）：
        - 历史兼容/修复：允许显式 id/sku
        - 默认必须禁止，避免被误用为“改码工具”
        - 仅当设置环境变量 WMS_ALLOW_CREATE_ITEM_BY_ID=1 时才允许调用
        """
        if not _allow_create_item_by_id():
            raise ValueError("create_item_by_id disabled: set WMS_ALLOW_CREATE_ITEM_BY_ID=1 to enable for maintenance")

        if not id or id <= 0:
            raise ValueError("id 必须为正整数")

        # ✅ 若已存在：只返回，不覆盖、不改码
        exists = self.db.get(Item, id)
        if exists is not None:
            return decorate_rules(exists)

        sku_val = (sku or str(id)).strip()
        if not sku_val:
            raise ValueError("sku is required for create_item_by_id (maintenance path)")

        name_val = (name or f"ITEM-{id}").strip()
        spec_val = spec.strip() if isinstance(spec, str) else None
        unit_val = (uom or "PCS").strip().upper() or "PCS"
        enabled_val = True if enabled is None else bool(enabled)

        brand_val = brand.strip() if isinstance(brand, str) and brand.strip() else None
        category_val = category.strip() if isinstance(category, str) and category.strip() else None

        obj = Item(
            id=id,
            sku=sku_val,
            name=name_val,
            unit=unit_val,
            spec=spec_val,
            enabled=enabled_val,
            supplier_id=supplier_id,
            brand=brand_val,
            category=category_val,
            has_shelf_life=bool(has_shelf_life) if has_shelf_life is not None else False,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
        )

        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "items_pkey" in raw:
                raise ValueError(f"Item id {id} already exists") from e
            if "items_sku_key" in raw or ("unique" in raw and "sku" in raw):
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return decorate_rules(obj)

    def get_items(
        self,
        *,
        supplier_id: Optional[int] = None,
        enabled: Optional[bool] = None,
        q: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Item]:
        rows = repo_get_items(self.db, supplier_id=supplier_id, enabled=enabled, q=q, limit=limit)
        return [decorate_rules(r) for r in rows]

    # 兼容旧接口：保留原方法名
    def get_all_items(self) -> List[Item]:
        return self.get_items()

    def get_item_by_id(self, id: int) -> Optional[Item]:
        obj = repo_get_item_by_id(self.db, id)
        return decorate_rules(obj) if obj else None

    def get_item_by_sku(self, sku: str) -> Optional[Item]:
        obj = repo_get_item_by_sku(self.db, sku)
        return decorate_rules(obj) if obj else None

    def update_item(
        self,
        *,
        id: int,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        enabled: Optional[bool] = None,
        supplier_id: Optional[int] = None,
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        brand_set: bool = False,
        category_set: bool = False,
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

        if has_shelf_life is not None:
            obj.has_shelf_life = bool(has_shelf_life)
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

        if brand_set:
            obj.brand = brand.strip() if isinstance(brand, str) and brand.strip() else None
            changed = True

        if category_set:
            obj.category = category.strip() if isinstance(category, str) and category.strip() else None
            changed = True

        if not changed:
            return decorate_rules(obj)

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return decorate_rules(obj)
