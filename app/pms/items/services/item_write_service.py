# app/pms/items/services/item_write_service.py
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.repos.item_uom_repo import create_item_uom
from app.pms.items.repos.item_write_repo import (
    add_item,
    commit as repo_commit,
    flush as repo_flush,
    get_item_by_id_for_update,
    refresh_item,
    rollback as repo_rollback,
)
from app.pms.items.services.item_sku_code_service import ItemSkuCodeService


_ALLOWED_LOT_SOURCE_POLICIES = {"INTERNAL_ONLY", "SUPPLIER_ONLY"}
_ALLOWED_EXPIRY_POLICIES = {"NONE", "REQUIRED"}
_ALLOWED_SHELF_LIFE_UNITS = {"DAY", "WEEK", "MONTH", "YEAR"}
_SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,127}$")


def _norm_policy_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    return s if s else None


def _norm_text_or_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _validate_sku(v: str) -> str:
    s = str(v or "").strip().upper()
    if not s:
        raise ValueError("sku 不能为空")
    if len(s) > 128:
        raise ValueError("sku 长度不能超过 128")
    if not _SKU_PATTERN.fullmatch(s):
        raise ValueError("invalid sku")
    return s


def _norm_shelf_life_unit(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    if not s:
        return None
    if s not in _ALLOWED_SHELF_LIFE_UNITS:
        raise ValueError("invalid shelf_life_unit")
    return s


def _validate_lot_source_policy(v: Optional[str]) -> str:
    s = _norm_policy_str(v)
    if s is None:
        raise ValueError("lot_source_policy 不能为空")
    if s not in _ALLOWED_LOT_SOURCE_POLICIES:
        raise ValueError("invalid lot_source_policy")
    return s


def _validate_expiry_policy(v: Optional[str]) -> str:
    s = _norm_policy_str(v)
    if s is None:
        raise ValueError("expiry_policy 不能为空")
    if s not in _ALLOWED_EXPIRY_POLICIES:
        raise ValueError("invalid expiry_policy")
    return s


def _resolve_shelf_life_pair(
    *,
    expiry_policy: str,
    current_value: Optional[int],
    current_unit: Optional[str],
    shelf_life_value: Optional[int],
    shelf_life_value_set: bool,
    shelf_life_unit: Optional[str],
    shelf_life_unit_set: bool,
) -> tuple[Optional[int], Optional[str]]:
    if expiry_policy != "REQUIRED":
        return None, None

    next_value = current_value
    next_unit = _norm_shelf_life_unit(current_unit) if current_unit is not None else None

    if shelf_life_value_set:
        if shelf_life_value is not None and int(shelf_life_value) <= 0:
            raise ValueError("shelf_life_value must be > 0")
        next_value = int(shelf_life_value) if shelf_life_value is not None else None
        if shelf_life_value is None:
            next_unit = None

    if shelf_life_unit_set:
        next_unit = _norm_shelf_life_unit(shelf_life_unit)
        if shelf_life_unit is None:
            next_value = None

    if (next_value is None) != (next_unit is None):
        raise ValueError("shelf_life_value and shelf_life_unit must be both set or both null")

    return next_value, next_unit


class ItemWriteService:
    """
    写入层（Write）：

    - 负责 Item 本体（public.items）的 create/update + 事务边界
    - 负责字段归一、默认值、补丁语义
    - 不负责 HTTP 兼容字段
    - 不负责输出投影
    - 不负责 item_uoms / item_barcodes 的聚合编排
    - 持久化动作交给 repos/item_write_repo.py

    终态收口：
    - items.uom / items.case_* / items.weight_kg 已移除
    - 包装、单位、净重、条码属于商品聚合的其他真相源
    - owner 聚合写接口应在更高一层 orchestrate item + item_uoms + item_barcodes

    主合同语义：
    - POST /items 必须显式传 sku
    - 创建 item 时仍自动补最小 base item_uom
    - 创建 item 时同步写 item_sku_codes PRIMARY，items.sku 仅作为当前主 SKU 投影
    """

    def __init__(self, db: Session) -> None:
        self.db = db

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
        sku_val = _validate_sku(sku)

        name_val = _norm_text_or_none(name)
        if not name_val:
            raise ValueError("name is required")

        spec_val = _norm_text_or_none(spec)
        brand_val = _norm_text_or_none(brand)
        category_val = _norm_text_or_none(category)

        lot_policy = _norm_policy_str(lot_source_policy) or "SUPPLIER_ONLY"
        if lot_policy not in _ALLOWED_LOT_SOURCE_POLICIES:
            raise ValueError("invalid lot_source_policy")

        exp_policy = _norm_policy_str(expiry_policy) or "NONE"
        if exp_policy not in _ALLOWED_EXPIRY_POLICIES:
            raise ValueError("invalid expiry_policy")

        deriv_allowed = True if derivation_allowed is None else bool(derivation_allowed)
        uom_gov = False if uom_governance_enabled is None else bool(uom_governance_enabled)

        if shelf_life_value is not None and int(shelf_life_value) <= 0:
            raise ValueError("shelf_life_value must be > 0")

        sl_unit = _norm_shelf_life_unit(shelf_life_unit)

        if exp_policy != "REQUIRED":
            sl_value = None
            sl_unit = None
        else:
            sl_value = int(shelf_life_value) if shelf_life_value is not None else None
            if (sl_value is None) != (sl_unit is None):
                raise ValueError("shelf_life_value and shelf_life_unit must be both set or both null")

        obj = Item(
            sku=sku_val,
            name=name_val,
            spec=spec_val,
            enabled=bool(enabled),
            supplier_id=supplier_id,
            brand=brand_val,
            category=category_val,
            lot_source_policy=lot_policy,
            expiry_policy=exp_policy,
            derivation_allowed=deriv_allowed,
            uom_governance_enabled=uom_gov,
            shelf_life_value=sl_value,
            shelf_life_unit=sl_unit,
        )

        add_item(self.db, obj)
        try:
            repo_flush(self.db)

            ItemSkuCodeService(self.db).create_primary_code_in_current_tx(
                item_id=int(obj.id),
                code=sku_val,
                remark="created with item",
            )

            # 维持当前主合同语义：创建 item 时自动补最小 base item_uom
            create_item_uom(
                self.db,
                item_id=int(obj.id),
                uom="PCS",
                ratio_to_base=1,
                display_name="PCS",
                net_weight_kg=None,
                is_base=True,
                is_purchase_default=True,
                is_inbound_default=True,
                is_outbound_default=True,
            )

            repo_flush(self.db)
            repo_commit(self.db)
        except IntegrityError as e:
            repo_rollback(self.db)
            raw = str(getattr(e, "orig", e)).lower()
            if (
                "items_sku_key" in raw
                or "uq_item_sku_codes_code" in raw
                or ("unique" in raw and "sku" in raw)
            ):
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e
        except ValueError as e:
            repo_rollback(self.db)
            if str(e) == "SKU code duplicate":
                raise ValueError("SKU duplicate") from e
            raise

        refresh_item(self.db, obj)
        return obj

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
        obj = get_item_by_id_for_update(self.db, int(id))
        if obj is None:
            raise ValueError("Item not found")

        changed = False

        if name_set:
            new_name = _norm_text_or_none(name)
            if not new_name:
                raise ValueError("name 不能为空")
            obj.name = new_name
            changed = True

        if spec_set:
            obj.spec = _norm_text_or_none(spec)
            changed = True

        if enabled_set:
            if enabled is None:
                raise ValueError("enabled 不能为空")
            obj.enabled = bool(enabled)
            changed = True

        if supplier_id_set:
            obj.supplier_id = supplier_id
            changed = True

        if lot_source_policy_set:
            obj.lot_source_policy = _validate_lot_source_policy(lot_source_policy)
            changed = True

        current_expiry_policy = _norm_policy_str(getattr(obj, "expiry_policy", None))
        if current_expiry_policy is None:
            raise ValueError("item expiry_policy is invalid")

        next_expiry_policy = current_expiry_policy
        if expiry_policy_set:
            next_expiry_policy = _validate_expiry_policy(expiry_policy)
            obj.expiry_policy = next_expiry_policy
            changed = True

        if derivation_allowed_set:
            if derivation_allowed is None:
                raise ValueError("derivation_allowed 不能为空")
            obj.derivation_allowed = bool(derivation_allowed)
            changed = True

        if uom_governance_enabled_set:
            if uom_governance_enabled is None:
                raise ValueError("uom_governance_enabled 不能为空")
            obj.uom_governance_enabled = bool(uom_governance_enabled)
            changed = True

        if brand_set:
            obj.brand = _norm_text_or_none(brand)
            changed = True

        if category_set:
            obj.category = _norm_text_or_none(category)
            changed = True

        if expiry_policy_set or shelf_life_value_set or shelf_life_unit_set:
            resolved_value, resolved_unit = _resolve_shelf_life_pair(
                expiry_policy=next_expiry_policy,
                current_value=(
                    int(obj.shelf_life_value)
                    if getattr(obj, "shelf_life_value", None) is not None
                    else None
                ),
                current_unit=(
                    str(obj.shelf_life_unit)
                    if getattr(obj, "shelf_life_unit", None) is not None
                    else None
                ),
                shelf_life_value=shelf_life_value,
                shelf_life_value_set=shelf_life_value_set,
                shelf_life_unit=shelf_life_unit,
                shelf_life_unit_set=shelf_life_unit_set,
            )
            obj.shelf_life_value = resolved_value
            obj.shelf_life_unit = resolved_unit
            changed = True

        if not changed:
            return obj

        try:
            repo_commit(self.db)
        except IntegrityError as e:
            repo_rollback(self.db)
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        refresh_item(self.db, obj)
        return obj
