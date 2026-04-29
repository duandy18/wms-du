# app/pms/items/services/item_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.services.item_presenter import ItemPresenter
from app.pms.items.services.item_query_service import ItemQueryService
from app.pms.items.services.item_write_service import ItemWriteService


class ItemService:
    """
    门面（Facade）：

    - 内部按功能拆分到：Query / Write / Presenter
    - 主合同写入语义通过 ItemWriteService 统一收口
    - create_item_by_id 历史修复通道已退役，不再保留内部兼容入口

    Phase M-3：
    - items.case_ratio / items.case_uom 已删除；包装单位/倍率请走 item_uoms

    Phase M-5：
    - items.uom 已物理移除；单位治理完全由 item_uoms 承载

    Phase M-6：
    - items.weight_kg 不再作为写入真相源
    - PMS 主合同的净重读写转移到 base item_uom.net_weight_kg

    SKU coding：
    - 主合同 POST /items 不再自动生成 SKU
    - items.sku 必须由调用方显式输入，通常来自 SKU 编码页生成候选后人工确认

    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._query = ItemQueryService(db)
        self._write = ItemWriteService(db)
        self._present = ItemPresenter(db)

    def create_item(
        self,
        *,
        sku: str,
        name: str,
        spec: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        enabled: bool = True,
        supplier_id: Optional[int] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        lot_source_policy: Optional[str] = None,
        expiry_policy: Optional[str] = None,
        derivation_allowed: Optional[bool] = None,
        uom_governance_enabled: Optional[bool] = None,
    ) -> Item:
        obj = self._write.create_item(
            sku=sku,
            name=name,
            spec=spec,
            brand=brand,
            category=category,
            enabled=enabled,
            supplier_id=supplier_id,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            lot_source_policy=lot_source_policy,
            expiry_policy=expiry_policy,
            derivation_allowed=derivation_allowed,
            uom_governance_enabled=uom_governance_enabled,
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
