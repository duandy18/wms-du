# app/services/item_maintenance_service.py
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.item import Item
from app.services.item_barcode_service import ItemBarcodeService


def _allow_create_item_by_id() -> bool:
    return os.getenv("WMS_ALLOW_CREATE_ITEM_BY_ID", "").strip() == "1"


class ItemMaintenanceService:
    """
    运维/修复通道（Maintenance）：

    - create_item_by_id：历史兼容/修复
    - 默认关闭（WMS_ALLOW_CREATE_ITEM_BY_ID=1 才允许）
    - 不承担正常业务 create/update
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._barcodes = ItemBarcodeService(db)

    def create_item_by_id(
        self,
        *,
        id: int,
        sku: Optional[str] = None,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        case_ratio: Optional[int] = None,
        case_uom: Optional[str] = None,
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
        if not _allow_create_item_by_id():
            raise ValueError("create_item_by_id disabled: set WMS_ALLOW_CREATE_ITEM_BY_ID=1 to enable for maintenance")

        if not id or id <= 0:
            raise ValueError("id 必须为正整数")

        exists = self.db.get(Item, int(id))
        if exists is not None:
            return exists

        sku_val = (sku or str(id)).strip()
        if not sku_val:
            raise ValueError("sku is required for create_item_by_id (maintenance path)")

        name_val = (name or f"ITEM-{id}").strip()
        spec_val = spec.strip() if isinstance(spec, str) else None
        unit_val = (uom or "PCS").strip().upper() or "PCS"
        enabled_val = True if enabled is None else bool(enabled)

        brand_val = brand.strip() if isinstance(brand, str) and brand.strip() else None
        category_val = category.strip() if isinstance(category, str) and category.strip() else None

        case_ratio_val: Optional[int] = None
        if case_ratio is not None:
            if int(case_ratio) < 1:
                raise ValueError("case_ratio must be >= 1")
            case_ratio_val = int(case_ratio)

        case_uom_val = case_uom.strip() if isinstance(case_uom, str) and case_uom.strip() else None

        obj = Item(
            id=int(id),
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
            case_ratio=case_ratio_val,
            case_uom=case_uom_val,
        )

        self.db.add(obj)
        try:
            self.db.flush()

            code = (barcode or "").strip()
            if code:
                self._barcodes.create_primary_for_item(item_id=int(obj.id), barcode=code, kind="EAN13")

            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "items_pkey" in raw:
                raise ValueError(f"Item id {id} already exists") from e
            if "items_sku_key" in raw or ("unique" in raw and "sku" in raw):
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e
        except ValueError:
            self.db.rollback()
            raise

        self.db.refresh(obj)
        return obj
