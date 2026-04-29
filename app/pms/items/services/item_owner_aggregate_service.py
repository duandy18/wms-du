# app/pms/items/services/item_owner_aggregate_service.py
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.contracts.item_aggregate import (
    AggregateBarcodeInput,
    AggregateItemInput,
    AggregateUomInput,
    ItemAggregateOut,
    ItemAggregatePayload,
)
from app.pms.items.repos.item_aggregate_read_repo import get_item_aggregate_record
from app.pms.items.repos.item_barcode_repo import (
    clear_primary_flags_for_item,
    create_item_barcode,
    delete_item_barcode,
    get_item_barcode_by_code,
    get_item_barcode_by_id,
    has_barcode_bound_to_item_uom,
    list_item_barcodes_by_item_id,
    refresh_item_barcode,
    update_item_barcode_fields,
)
from app.pms.items.repos.item_uom_repo import (
    create_item_uom,
    delete_item_uom,
    has_barcode_refs_for_item_uom,
    has_po_line_refs_for_item_uom,
    has_receipt_line_refs_for_item_uom,
    list_item_uoms_by_item_id,
    refresh_item_uom,
    update_item_uom_fields,
)
from app.pms.items.repos.item_write_repo import (
    add_item,
    commit as repo_commit,
    flush as repo_flush,
    get_item_by_id_for_update,
    refresh_item,
    rollback as repo_rollback,
)
from app.pms.items.services.item_presenter import ItemPresenter


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


def _validate_sku(v: object) -> str:
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


def _resolve_item_fields(item_in: AggregateItemInput) -> dict[str, object]:
    sku_val = _validate_sku(item_in.sku)

    name_val = _norm_text_or_none(item_in.name)
    if not name_val:
        raise ValueError("name is required")

    spec_val = _norm_text_or_none(item_in.spec)
    brand_val = _norm_text_or_none(item_in.brand)
    category_val = _norm_text_or_none(item_in.category)

    lot_policy = _norm_policy_str(item_in.lot_source_policy) or "SUPPLIER_ONLY"
    if lot_policy not in _ALLOWED_LOT_SOURCE_POLICIES:
        raise ValueError("invalid lot_source_policy")

    exp_policy = _norm_policy_str(item_in.expiry_policy) or "NONE"
    if exp_policy not in _ALLOWED_EXPIRY_POLICIES:
        raise ValueError("invalid expiry_policy")

    deriv_allowed = True if item_in.derivation_allowed is None else bool(item_in.derivation_allowed)
    uom_gov = False if item_in.uom_governance_enabled is None else bool(item_in.uom_governance_enabled)

    if item_in.shelf_life_value is not None and int(item_in.shelf_life_value) <= 0:
        raise ValueError("shelf_life_value must be > 0")

    sl_unit = _norm_shelf_life_unit(item_in.shelf_life_unit)

    if exp_policy != "REQUIRED":
        sl_value = None
        sl_unit = None
    else:
        sl_value = int(item_in.shelf_life_value) if item_in.shelf_life_value is not None else None
        if (sl_value is None) != (sl_unit is None):
            raise ValueError("shelf_life_value and shelf_life_unit must be both set or both null")

    return {
        "sku": sku_val,
        "name": name_val,
        "spec": spec_val,
        "brand": brand_val,
        "category": category_val,
        "enabled": bool(item_in.enabled),
        "supplier_id": item_in.supplier_id,
        "lot_source_policy": lot_policy,
        "expiry_policy": exp_policy,
        "derivation_allowed": deriv_allowed,
        "uom_governance_enabled": uom_gov,
        "shelf_life_value": sl_value,
        "shelf_life_unit": sl_unit,
    }


class ItemOwnerAggregateService:
    """
    商品 owner 聚合写服务：

    - 一次处理 item + item_uoms + item_barcodes
    - 事务边界在 service
    - 前端不再自己 orchestrate 多接口写入

    终态语义：
    - create / replace 都要求提交完整商品聚合
    - POST /items/aggregate：完整创建
    - PUT /items/{id}/aggregate：严格 full replace
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._present = ItemPresenter(db)

    def get_aggregate(self, *, item_id: int) -> ItemAggregateOut:
        record = get_item_aggregate_record(
            self.db,
            item_id=int(item_id),
            active_only=None,
        )
        if record is None:
            raise ValueError("Item not found")

        presented = self._present.present_item(item=record.item)
        assert presented is not None

        return ItemAggregateOut(
            item=presented,
            uoms=record.uoms,
            barcodes=record.barcodes,
        )

    def create_aggregate(self, *, payload: ItemAggregatePayload) -> ItemAggregateOut:
        item_fields = _resolve_item_fields(payload.item)

        obj = Item(
            sku=str(item_fields["sku"]),
            name=str(item_fields["name"]),
            spec=item_fields["spec"],
            enabled=bool(item_fields["enabled"]),
            supplier_id=item_fields["supplier_id"],
            brand=item_fields["brand"],
            category=item_fields["category"],
            lot_source_policy=str(item_fields["lot_source_policy"]),
            expiry_policy=str(item_fields["expiry_policy"]),
            derivation_allowed=bool(item_fields["derivation_allowed"]),
            uom_governance_enabled=bool(item_fields["uom_governance_enabled"]),
            shelf_life_value=item_fields["shelf_life_value"],
            shelf_life_unit=item_fields["shelf_life_unit"],
        )

        add_item(self.db, obj)

        try:
            repo_flush(self.db)

            uom_key_to_id, _keep_uom_ids = self._upsert_uoms(
                item_id=int(obj.id),
                payload_uoms=list(payload.uoms),
                existing_uoms=[],
            )

            self._sync_barcodes(
                item_id=int(obj.id),
                payload_barcodes=list(payload.barcodes),
                uom_key_to_id=uom_key_to_id,
                existing_barcodes=[],
            )

            repo_commit(self.db)
        except IntegrityError as e:
            repo_rollback(self.db)
            raw = str(getattr(e, "orig", e)).lower()
            if "items_sku_key" in raw or ("unique" in raw and "sku" in raw):
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e
        except ValueError:
            repo_rollback(self.db)
            raise

        refresh_item(self.db, obj)
        return self.get_aggregate(item_id=int(obj.id))

    def replace_aggregate(
        self,
        *,
        item_id: int,
        payload: ItemAggregatePayload,
    ) -> ItemAggregateOut:
        obj = get_item_by_id_for_update(self.db, int(item_id))
        if obj is None:
            raise ValueError("Item not found")

        item_fields = _resolve_item_fields(payload.item)

        if str(item_fields["sku"]) != str(obj.sku):
            raise ValueError("sku cannot be changed")

        obj.name = str(item_fields["name"])
        obj.spec = item_fields["spec"]
        obj.enabled = bool(item_fields["enabled"])
        obj.supplier_id = item_fields["supplier_id"]
        obj.brand = item_fields["brand"]
        obj.category = item_fields["category"]
        obj.lot_source_policy = str(item_fields["lot_source_policy"])
        obj.expiry_policy = str(item_fields["expiry_policy"])
        obj.derivation_allowed = bool(item_fields["derivation_allowed"])
        obj.uom_governance_enabled = bool(item_fields["uom_governance_enabled"])
        obj.shelf_life_value = item_fields["shelf_life_value"]
        obj.shelf_life_unit = item_fields["shelf_life_unit"]

        existing_uoms = list_item_uoms_by_item_id(self.db, int(item_id))
        existing_barcodes = list_item_barcodes_by_item_id(self.db, item_id=int(item_id), active_only=None)

        try:
            uom_key_to_id, keep_uom_ids = self._upsert_uoms(
                item_id=int(item_id),
                payload_uoms=list(payload.uoms),
                existing_uoms=existing_uoms,
            )

            self._sync_barcodes(
                item_id=int(item_id),
                payload_barcodes=list(payload.barcodes),
                uom_key_to_id=uom_key_to_id,
                existing_barcodes=existing_barcodes,
            )

            self._cleanup_obsolete_uoms(
                existing_uoms=existing_uoms,
                keep_uom_ids=keep_uom_ids,
            )

            repo_commit(self.db)
        except IntegrityError as e:
            repo_rollback(self.db)
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e
        except ValueError:
            repo_rollback(self.db)
            raise

        refresh_item(self.db, obj)
        return self.get_aggregate(item_id=int(item_id))

    def _upsert_uoms(
        self,
        *,
        item_id: int,
        payload_uoms: list[AggregateUomInput],
        existing_uoms: list,
    ) -> tuple[dict[str, int], set[int]]:
        existing_by_id = {int(x.id): x for x in existing_uoms}
        keep_ids: set[int] = set()

        # 先清默认位，避免 partial unique index 冲突
        for u in existing_uoms:
            u.is_base = False
            u.is_purchase_default = False
            u.is_inbound_default = False
            u.is_outbound_default = False

        repo_flush(self.db)

        uom_key_to_id: dict[str, int] = {}

        for row in payload_uoms:
            if row.id is not None:
                obj = existing_by_id.get(int(row.id))
                if obj is None:
                    raise ValueError(f"ItemUom not found: id={int(row.id)}")
                keep_ids.add(int(obj.id))
                update_item_uom_fields(
                    obj,
                    uom=str(row.uom),
                    ratio_to_base=int(row.ratio_to_base),
                    display_name=row.display_name,
                    net_weight_kg=row.net_weight_kg,
                    is_base=bool(row.is_base),
                    is_purchase_default=bool(row.is_purchase_default),
                    is_inbound_default=bool(row.is_inbound_default),
                    is_outbound_default=bool(row.is_outbound_default),
                )
            else:
                obj = create_item_uom(
                    self.db,
                    item_id=int(item_id),
                    uom=str(row.uom),
                    ratio_to_base=int(row.ratio_to_base),
                    display_name=row.display_name,
                    net_weight_kg=row.net_weight_kg,
                    is_base=bool(row.is_base),
                    is_purchase_default=bool(row.is_purchase_default),
                    is_inbound_default=bool(row.is_inbound_default),
                    is_outbound_default=bool(row.is_outbound_default),
                )

            repo_flush(self.db)
            refresh_item_uom(self.db, obj)
            keep_ids.add(int(obj.id))
            uom_key_to_id[str(row.uom_key)] = int(obj.id)

        return uom_key_to_id, keep_ids

    def _sync_barcodes(
        self,
        *,
        item_id: int,
        payload_barcodes: list[AggregateBarcodeInput],
        uom_key_to_id: dict[str, int],
        existing_barcodes: list,
    ) -> None:
        existing_by_id = {int(x.id): x for x in existing_barcodes}

        incoming_ids = {int(x.id) for x in payload_barcodes if x.id is not None}
        for old in existing_barcodes:
            if int(old.id) not in incoming_ids:
                delete_item_barcode(self.db, old)

        repo_flush(self.db)

        has_primary = any(bool(x.is_primary) for x in payload_barcodes)
        if has_primary:
            clear_primary_flags_for_item(self.db, item_id=int(item_id))
            repo_flush(self.db)

        for row in payload_barcodes:
            target_uom_id = uom_key_to_id.get(str(row.bind_uom_key))
            if target_uom_id is None:
                raise ValueError(f"barcode 绑定失败：uom_key 不存在 {row.bind_uom_key}")

            if row.id is not None:
                obj = existing_by_id.get(int(row.id))
                if obj is None:
                    obj = get_item_barcode_by_id(self.db, int(row.id))
                if obj is None:
                    raise ValueError(f"Barcode not found: id={int(row.id)}")

                existing_same_code = get_item_barcode_by_code(
                    self.db,
                    barcode=str(row.barcode),
                    exclude_id=int(obj.id),
                )
                if existing_same_code is not None:
                    raise ValueError("Barcode already exists")

                if target_uom_id != int(obj.item_uom_id):
                    if has_barcode_bound_to_item_uom(
                        self.db,
                        item_id=int(item_id),
                        item_uom_id=int(target_uom_id),
                        exclude_barcode_id=int(obj.id),
                    ):
                        raise ValueError("Current item_uom already bound to a barcode")

                update_item_barcode_fields(
                    obj,
                    item_uom_id=int(target_uom_id),
                    barcode=str(row.barcode),
                    symbology=str(row.symbology),
                    active=bool(row.active),
                    is_primary=bool(row.is_primary),
                )
            else:
                existing_same_code = get_item_barcode_by_code(
                    self.db,
                    barcode=str(row.barcode),
                )
                if existing_same_code is not None:
                    raise ValueError("Barcode already exists")

                if has_barcode_bound_to_item_uom(
                    self.db,
                    item_id=int(item_id),
                    item_uom_id=int(target_uom_id),
                ):
                    raise ValueError("Current item_uom already bound to a barcode")

                obj = create_item_barcode(
                    self.db,
                    item_id=int(item_id),
                    item_uom_id=int(target_uom_id),
                    barcode=str(row.barcode),
                    symbology=str(row.symbology),
                    active=bool(row.active),
                    is_primary=bool(row.is_primary),
                )
                repo_flush(self.db)
                refresh_item_barcode(self.db, obj)

    def _cleanup_obsolete_uoms(
        self,
        *,
        existing_uoms: list,
        keep_uom_ids: set[int],
    ) -> None:
        for old in existing_uoms:
            if int(old.id) in keep_uom_ids:
                continue

            if has_barcode_refs_for_item_uom(
                self.db,
                item_id=int(old.item_id),
                item_uom_id=int(old.id),
            ):
                raise ValueError("当前包装已绑定条码，不能删除；请先修改条码绑定")

            if has_po_line_refs_for_item_uom(self.db, item_uom_id=int(old.id)):
                raise ValueError("当前包装已被采购单引用，不能删除")

            if has_receipt_line_refs_for_item_uom(self.db, item_uom_id=int(old.id)):
                raise ValueError("当前包装已被收货记录引用，不能删除")

            delete_item_uom(self.db, old)
