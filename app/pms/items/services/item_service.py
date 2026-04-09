# app/pms/items/services/item_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.item import Item
from app.pms.items.services.item_maintenance_service import ItemMaintenanceService
from app.pms.items.services.item_presenter import ItemPresenter
from app.pms.items.services.item_query_service import ItemQueryService
from app.pms.items.services.item_test_set_service import ItemTestSetService
from app.pms.items.services.item_write_service import ItemWriteService


class ItemService:
    """
    门面（Facade）：

    - 内部按功能拆分到：Query / Write / Presenter / TestSet / Maintenance
    - 主合同写入语义通过 ItemWriteService 统一收口
    - 例外修复通道（create_item_by_id）仍走 Maintenance

    Phase M-3：
    - items.case_ratio / items.case_uom 已删除；包装单位/倍率请走 item_uoms

    Phase M-5：
    - items.uom 已物理移除；单位治理完全由 item_uoms 承载
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._query = ItemQueryService(db)
        self._write = ItemWriteService(db)
        self._present = ItemPresenter(db)
        self._test_sets = ItemTestSetService(db)
        self._maintenance = ItemMaintenanceService(db)

    def next_sku(self) -> str:
        return self._write.next_sku()

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

    def create_item(
        self,
        *,
        name: str,
        spec: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        enabled: bool = True,
        supplier_id: Optional[int] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
        lot_source_policy: Optional[str] = None,
        expiry_policy: Optional[str] = None,
        derivation_allowed: Optional[bool] = None,
        uom_governance_enabled: Optional[bool] = None,
    ) -> Item:
        obj = self._write.create_item(
            name=name,
            spec=spec,
            brand=brand,
            category=category,
            enabled=enabled,
            supplier_id=supplier_id,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
            lot_source_policy=lot_source_policy,
            expiry_policy=expiry_policy,
            derivation_allowed=derivation_allowed,
            uom_governance_enabled=uom_governance_enabled,
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
        name_set: bool = False,
        spec: Optional[str] = None,
        spec_set: bool = False,
        enabled: Optional[bool] = None,
        enabled_set: bool = False,
        supplier_id: Optional[int] = None,
        supplier_id_set: bool = False,
        shelf_life_value: Optional[int] = None,
        shelf_life_value_set: bool = False,
        shelf_life_unit: Optional[str] = None,
        shelf_life_unit_set: bool = False,
        weight_kg: Optional[float] = None,
        weight_kg_set: bool = False,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        brand_set: bool = False,
        category_set: bool = False,
        lot_source_policy: Optional[str] = None,
        lot_source_policy_set: bool = False,
        expiry_policy: Optional[str] = None,
        expiry_policy_set: bool = False,
        derivation_allowed: Optional[bool] = None,
        derivation_allowed_set: bool = False,
        uom_governance_enabled: Optional[bool] = None,
        uom_governance_enabled_set: bool = False,
    ) -> Item:
        obj = self._write.update_item(
            id=id,
            name=name,
            name_set=name_set,
            spec=spec,
            spec_set=spec_set,
            enabled=enabled,
            enabled_set=enabled_set,
            supplier_id=supplier_id,
            supplier_id_set=supplier_id_set,
            shelf_life_value=shelf_life_value,
            shelf_life_value_set=shelf_life_value_set,
            shelf_life_unit=shelf_life_unit,
            shelf_life_unit_set=shelf_life_unit_set,
            weight_kg=weight_kg,
            weight_kg_set=weight_kg_set,
            brand=brand,
            category=category,
            brand_set=brand_set,
            category_set=category_set,
            lot_source_policy=lot_source_policy,
            lot_source_policy_set=lot_source_policy_set,
            expiry_policy=expiry_policy,
            expiry_policy_set=expiry_policy_set,
            derivation_allowed=derivation_allowed,
            derivation_allowed_set=derivation_allowed_set,
            uom_governance_enabled=uom_governance_enabled,
            uom_governance_enabled_set=uom_governance_enabled_set,
        )
        out = self._present.present_item(item=obj)
        assert out is not None
        return out
