# app/pms/public/items/services/item_aggregate_read_service.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.pms.items.repos.item_aggregate_read_repo import get_item_aggregate_record
from app.pms.public.items.contracts.item_aggregate import (
    PublicAggregateBarcode,
    PublicAggregateItem,
    PublicAggregateUom,
    PublicItemAggregateOut,
)


def _enum_value(v: object) -> str | None:
    if v is None:
        return None
    value = getattr(v, "value", v)
    return str(value) if value is not None else None


class ItemAggregateReadService:
    """
    PMS public aggregate read service。

    定位：
    - 对外提供商品完整读面（item + uoms + barcodes）
    - 不承载 owner presenter 语义
    - 不复用 owner aggregate contract
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_aggregate_by_id(self, *, item_id: int) -> PublicItemAggregateOut | None:
        record = get_item_aggregate_record(
            self.db,
            item_id=int(item_id),
            active_only=None,
        )
        if record is None:
            return None

        item = record.item

        lot_source_policy = _enum_value(getattr(item, "lot_source_policy", None))
        expiry_policy = _enum_value(getattr(item, "expiry_policy", None))
        shelf_life_unit = _enum_value(getattr(item, "shelf_life_unit", None))

        if lot_source_policy not in {"INTERNAL_ONLY", "SUPPLIER_ONLY"}:
            raise RuntimeError(
                f"unexpected lot_source_policy for item_id={int(item.id)}: {lot_source_policy!r}"
            )
        if expiry_policy not in {"NONE", "REQUIRED"}:
            raise RuntimeError(
                f"unexpected expiry_policy for item_id={int(item.id)}: {expiry_policy!r}"
            )
        if shelf_life_unit is not None and shelf_life_unit not in {"DAY", "WEEK", "MONTH", "YEAR"}:
            raise RuntimeError(
                f"unexpected shelf_life_unit for item_id={int(item.id)}: {shelf_life_unit!r}"
            )

        return PublicItemAggregateOut(
            item=PublicAggregateItem(
                id=int(item.id),
                sku=str(item.sku),
                name=str(item.name),
                spec=str(item.spec).strip() if getattr(item, "spec", None) is not None else None,
                enabled=bool(item.enabled),
                supplier_id=(
                    int(item.supplier_id)
                    if getattr(item, "supplier_id", None) is not None
                    else None
                ),
                brand=str(item.brand).strip() if getattr(item, "brand", None) is not None else None,
                category=(
                    str(item.category).strip()
                    if getattr(item, "category", None) is not None
                    else None
                ),
                lot_source_policy=lot_source_policy,
                expiry_policy=expiry_policy,
                derivation_allowed=bool(getattr(item, "derivation_allowed")),
                uom_governance_enabled=bool(getattr(item, "uom_governance_enabled")),
                shelf_life_value=(
                    int(item.shelf_life_value)
                    if getattr(item, "shelf_life_value", None) is not None
                    else None
                ),
                shelf_life_unit=shelf_life_unit,
            ),
            uoms=[
                PublicAggregateUom(
                    id=int(u.id),
                    item_id=int(u.item_id),
                    uom=str(u.uom),
                    ratio_to_base=int(u.ratio_to_base),
                    display_name=(
                        str(u.display_name).strip()
                        if getattr(u, "display_name", None) is not None
                        else None
                    ),
                    net_weight_kg=(
                        float(u.net_weight_kg)
                        if getattr(u, "net_weight_kg", None) is not None
                        else None
                    ),
                    is_base=bool(u.is_base),
                    is_purchase_default=bool(u.is_purchase_default),
                    is_inbound_default=bool(u.is_inbound_default),
                    is_outbound_default=bool(u.is_outbound_default),
                )
                for u in record.uoms
            ],
            barcodes=[
                PublicAggregateBarcode(
                    id=int(b.id),
                    item_id=int(b.item_id),
                    item_uom_id=int(b.item_uom_id),
                    barcode=str(b.barcode),
                    symbology=str(b.symbology),
                    active=bool(b.active),
                    is_primary=bool(b.is_primary),
                )
                for b in record.barcodes
            ],
        )
