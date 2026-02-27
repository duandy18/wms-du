# app/services/item_write_service.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.item import Item
from app.services.item_barcode_service import ItemBarcodeService
from app.services.item_sku import next_sku


def _norm_policy_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    return s if s else None


def _is_required_expiry_policy(v: Optional[str]) -> bool:
    return _norm_policy_str(v) == "REQUIRED"


class ItemWriteService:
    """
    写入层（Write）：

    - 负责 Item 的 create/update + 事务边界
    - create 时允许可选写入主条码（调用 ItemBarcodeService）
    - 不负责 decorate / test-set / 输出投影
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._barcodes = ItemBarcodeService(db)

    def next_sku(self) -> str:
        return next_sku(self.db)

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
        # legacy mirror + params
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
        # Phase M policy (truth)
        lot_source_policy: Optional[str] = None,
        expiry_policy: Optional[str] = None,
        derivation_allowed: Optional[bool] = None,
        uom_governance_enabled: Optional[bool] = None,
    ) -> Item:
        name_val = (name or "").strip()
        if not name_val:
            raise ValueError("name is required")

        spec_val = spec.strip() if isinstance(spec, str) else None
        uom_val = (uom or "PCS").strip().upper() or "PCS"

        brand_val = brand.strip() if isinstance(brand, str) and brand.strip() else None
        category_val = category.strip() if isinstance(category, str) and category.strip() else None

        case_ratio_val: Optional[int] = None
        if case_ratio is not None:
            if int(case_ratio) < 1:
                raise ValueError("case_ratio must be >= 1")
            case_ratio_val = int(case_ratio)

        case_uom_val = case_uom.strip() if isinstance(case_uom, str) and case_uom.strip() else None

        sku_val = self.next_sku()

        # -------------------------
        # Phase M: resolve policy
        # -------------------------
        lot_policy = _norm_policy_str(lot_source_policy) or "SUPPLIER_ONLY"

        # expiry_policy is truth; if absent, fall back to legacy has_shelf_life mapping
        exp_policy = _norm_policy_str(expiry_policy)
        if exp_policy is None:
            exp_policy = "REQUIRED" if bool(has_shelf_life) else "NONE"

        deriv_allowed = True if derivation_allowed is None else bool(derivation_allowed)
        uom_gov = False if uom_governance_enabled is None else bool(uom_governance_enabled)

        # mirror field (DB check locked)
        has_sl = _is_required_expiry_policy(exp_policy)

        # if NONE, shelf_life params must be null (DB check ck_items_expiry_policy_vs_shelf_life)
        sl_value = shelf_life_value
        sl_unit = shelf_life_unit
        if not has_sl:
            sl_value = None
            sl_unit = None

        obj = Item(
            sku=sku_val,
            name=name_val,
            uom=uom_val,
            spec=spec_val,
            enabled=bool(enabled),
            supplier_id=supplier_id,
            brand=brand_val,
            category=category_val,
            # Phase M rule layer
            lot_source_policy=lot_policy,
            expiry_policy=exp_policy,
            derivation_allowed=deriv_allowed,
            uom_governance_enabled=uom_gov,
            # legacy mirror + params
            has_shelf_life=has_sl,
            shelf_life_value=sl_value,
            shelf_life_unit=sl_unit,
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
            if "items_sku_key" in raw or ("unique" in raw and "sku" in raw):
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e
        except ValueError:
            self.db.rollback()
            raise

        self.db.refresh(obj)
        return obj

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
        # legacy mirror + params
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        brand_set: bool = False,
        category_set: bool = False,
        # Phase M policy
        lot_source_policy: Optional[str] = None,
        expiry_policy: Optional[str] = None,
        derivation_allowed: Optional[bool] = None,
        uom_governance_enabled: Optional[bool] = None,
    ) -> Item:
        obj = self.db.get(Item, int(id))
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
            uom_val = (uom or "PCS").strip().upper() or "PCS"
            obj.uom = uom_val
            changed = True

        if case_ratio_set:
            if case_ratio is None:
                obj.case_ratio = None
            else:
                if int(case_ratio) < 1:
                    raise ValueError("case_ratio must be >= 1")
                obj.case_ratio = int(case_ratio)
            changed = True

        if case_uom_set:
            obj.case_uom = case_uom.strip() if isinstance(case_uom, str) and case_uom.strip() else None
            changed = True

        if enabled is not None:
            obj.enabled = bool(enabled)
            changed = True

        if supplier_id is not None:
            obj.supplier_id = supplier_id
            changed = True

        # -------------------------
        # Phase M policy updates
        # -------------------------
        if lot_source_policy is not None:
            obj.lot_source_policy = _norm_policy_str(lot_source_policy) or obj.lot_source_policy
            changed = True

        # expiry_policy takes precedence; if absent but has_shelf_life provided, derive it
        exp_policy = _norm_policy_str(expiry_policy)
        if exp_policy is None and has_shelf_life is not None:
            exp_policy = "REQUIRED" if bool(has_shelf_life) else "NONE"

        if exp_policy is not None:
            obj.expiry_policy = exp_policy
            # mirror
            obj.has_shelf_life = _is_required_expiry_policy(exp_policy)
            # enforce param clearing when NONE
            if not obj.has_shelf_life:
                obj.shelf_life_value = None
                obj.shelf_life_unit = None
            changed = True
        else:
            # no expiry_policy change; still allow updating mirror (but keep it consistent)
            if has_shelf_life is not None:
                # derive policy from mirror to satisfy DB CHECK
                derived = "REQUIRED" if bool(has_shelf_life) else "NONE"
                obj.expiry_policy = derived
                obj.has_shelf_life = _is_required_expiry_policy(derived)
                if not obj.has_shelf_life:
                    obj.shelf_life_value = None
                    obj.shelf_life_unit = None
                changed = True

        if derivation_allowed is not None:
            obj.derivation_allowed = bool(derivation_allowed)
            changed = True

        if uom_governance_enabled is not None:
            obj.uom_governance_enabled = bool(uom_governance_enabled)
            changed = True

        # shelf_life params updates (only meaningful when REQUIRED)
        if shelf_life_value is not None:
            if _is_required_expiry_policy(getattr(obj, "expiry_policy", None)):
                obj.shelf_life_value = shelf_life_value
            else:
                obj.shelf_life_value = None
            changed = True

        if shelf_life_unit is not None:
            if _is_required_expiry_policy(getattr(obj, "expiry_policy", None)):
                obj.shelf_life_unit = shelf_life_unit
            else:
                obj.shelf_life_unit = None
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
            return obj

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return obj
