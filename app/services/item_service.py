# app/services/item_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.item import Item
from app.services.item_maintenance_service import ItemMaintenanceService
from app.services.item_presenter import ItemPresenter
from app.services.item_query_service import ItemQueryService
from app.services.item_test_set_service import ItemTestSetService
from app.services.item_write_service import ItemWriteService


class ItemService:
    """
    门面（Facade）：

    - 对外保持现有接口不变（router 不用改）
    - 内部按功能拆分到：Query / Write / Presenter / TestSet / Maintenance
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._query = ItemQueryService(db)
        self._write = ItemWriteService(db)
        self._present = ItemPresenter(db)
        self._test_sets = ItemTestSetService(db)
        self._maintenance = ItemMaintenanceService(db)

    # 兼容 router：/items/sku/next
    def next_sku(self) -> str:
        return self._write.next_sku()

    # ---------- Test Set toggles（事务在这里收口） ----------
    def enable_item_test_flag(self, *, item_id: int, set_code: str = "DEFAULT") -> Item:
        obj = self.db.get(Item, int(item_id))
        if obj is None:
            raise ValueError("Item not found")

        try:
            self._test_sets.enable(item_id=int(item_id), set_code=set_code)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"DB error: {e}") from e

        self.db.refresh(obj)
        out = self._present.present_item(item=obj)
        assert out is not None
        return out

    def disable_item_test_flag(self, *, item_id: int, set_code: str = "DEFAULT") -> Item:
        obj = self.db.get(Item, int(item_id))
        if obj is None:
            raise ValueError("Item not found")

        try:
            self._test_sets.disable(item_id=int(item_id), set_code=set_code)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"DB error: {e}") from e

        self.db.refresh(obj)
        out = self._present.present_item(item=obj)
        assert out is not None
        return out

    # ---------- CRUD ----------
    def create_item(
        self,
        *,
        name: str,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        case_ratio: Optional[int] = None,
        case_uom: Optional[str] = None,
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
        obj = self._write.create_item(
            name=name,
            spec=spec,
            uom=uom,
            case_ratio=case_ratio,
            case_uom=case_uom,
            barcode=barcode,
            brand=brand,
            category=category,
            enabled=enabled,
            supplier_id=supplier_id,
            has_shelf_life=has_shelf_life,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
        )
        out = self._present.present_item(item=obj)
        assert out is not None
        return out

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
        obj = self._maintenance.create_item_by_id(
            id=id,
            sku=sku,
            name=name,
            spec=spec,
            uom=uom,
            case_ratio=case_ratio,
            case_uom=case_uom,
            barcode=barcode,
            brand=brand,
            category=category,
            enabled=enabled,
            supplier_id=supplier_id,
            has_shelf_life=has_shelf_life,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
        )
        out = self._present.present_item(item=obj)
        assert out is not None
        return out

    def get_items(
        self,
        *,
        supplier_id: Optional[int] = None,
        enabled: Optional[bool] = None,
        q: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Item]:
        rows = self._query.get_items(supplier_id=supplier_id, enabled=enabled, q=q, limit=limit)
        return self._present.present_items(items=rows)

    def get_all_items(self) -> List[Item]:
        return self.get_items()

    def get_item_by_id(self, id: int) -> Optional[Item]:
        obj = self._query.get_item_by_id(id)
        return self._present.present_item(item=obj)

    def get_item_by_sku(self, sku: str) -> Optional[Item]:
        obj = self._query.get_item_by_sku(sku)
        return self._present.present_item(item=obj)

    def update_item(
        self,
        *,
        id: int,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        case_ratio: Optional[int] = None,
        case_uom: Optional[str] = None,
        case_ratio_set: bool = False,
        case_uom_set: bool = False,
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
        obj = self._write.update_item(
            id=id,
            name=name,
            spec=spec,
            uom=uom,
            case_ratio=case_ratio,
            case_uom=case_uom,
            case_ratio_set=case_ratio_set,
            case_uom_set=case_uom_set,
            enabled=enabled,
            supplier_id=supplier_id,
            has_shelf_life=has_shelf_life,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
            brand=brand,
            category=category,
            brand_set=brand_set,
            category_set=category_set,
        )
        out = self._present.present_item(item=obj)
        assert out is not None
        return out
