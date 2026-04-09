# app/pms/public/items/services/item_read_service.py
from __future__ import annotations

from typing import Iterable, List

from sqlalchemy.orm import Session

from app.models.item import Item
from app.pms.items.repos.item_repo import get_item_by_id as repo_get_item_by_id
from app.pms.items.repos.item_repo import get_item_by_sku as repo_get_item_by_sku
from app.pms.items.repos.item_repo import get_items as repo_get_items
from app.pms.items.services.item_barcode_service import ItemBarcodeService
from app.pms.public.items.contracts.item_basic import ItemBasic
from app.pms.public.items.contracts.item_policy import ItemPolicy
from app.pms.public.items.contracts.item_query import ItemReadQuery


def _enum_value(v: object) -> str | None:
    if v is None:
        return None
    value = getattr(v, "value", v)
    return str(value) if value is not None else None


class ItemReadService:
    """
    PMS public read service。

    定位：
    - 供其他模块读取 PMS 商品最小事实
    - 不承载写入语义
    - 不暴露 owner 内部兼容输入逻辑
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._barcodes = ItemBarcodeService(db)

    def list_basic(self, *, query: ItemReadQuery | None = None) -> List[ItemBasic]:
        q = query or ItemReadQuery()
        rows = repo_get_items(
            self.db,
            supplier_id=q.supplier_id,
            enabled=q.enabled,
            q=q.q,
            limit=q.limit,
        )
        return self._map_items_to_basic(rows)

    def get_basic_by_id(self, *, item_id: int) -> ItemBasic | None:
        obj = repo_get_item_by_id(self.db, int(item_id))
        if obj is None:
            return None
        return self._map_item_to_basic(obj)

    def get_basic_by_sku(self, *, sku: str) -> ItemBasic | None:
        obj = repo_get_item_by_sku(self.db, sku)
        if obj is None:
            return None
        return self._map_item_to_basic(obj)

    def get_policy_by_id(self, *, item_id: int) -> ItemPolicy | None:
        obj = repo_get_item_by_id(self.db, int(item_id))
        if obj is None:
            return None
        return self._map_item_to_policy(obj)

    def get_policies_by_item_ids(self, *, item_ids: Iterable[int]) -> dict[int, ItemPolicy]:
        ids = sorted({int(x) for x in item_ids if x is not None})
        if not ids:
            return {}

        rows: list[Item] = []
        for item_id in ids:
            obj = repo_get_item_by_id(self.db, item_id)
            if obj is not None:
                rows.append(obj)

        return {int(x.id): self._map_item_to_policy(x) for x in rows}

    def _map_items_to_basic(self, items: list[Item]) -> List[ItemBasic]:
        if not items:
            return []

        barcode_map = self._barcodes.load_primary_barcodes_map(
            item_ids=[int(x.id) for x in items if getattr(x, "id", None) is not None]
        )
        return [self._build_item_basic(x, barcode_map.get(int(x.id))) for x in items]

    def _map_item_to_basic(self, item: Item) -> ItemBasic:
        barcode_map = self._barcodes.load_primary_barcodes_map(item_ids=[int(item.id)])
        return self._build_item_basic(item, barcode_map.get(int(item.id)))

    def _map_item_to_policy(self, item: Item) -> ItemPolicy:
        expiry_policy = _enum_value(getattr(item, "expiry_policy", None))
        lot_source_policy = _enum_value(getattr(item, "lot_source_policy", None))
        shelf_life_unit = _enum_value(getattr(item, "shelf_life_unit", None))

        if expiry_policy not in {"NONE", "REQUIRED"}:
            raise RuntimeError(f"unexpected expiry_policy for item_id={int(item.id)}: {expiry_policy!r}")
        if lot_source_policy not in {"INTERNAL_ONLY", "SUPPLIER_ONLY"}:
            raise RuntimeError(
                f"unexpected lot_source_policy for item_id={int(item.id)}: {lot_source_policy!r}"
            )
        if shelf_life_unit is not None and shelf_life_unit not in {"DAY", "WEEK", "MONTH", "YEAR"}:
            raise RuntimeError(
                f"unexpected shelf_life_unit for item_id={int(item.id)}: {shelf_life_unit!r}"
            )

        return ItemPolicy(
            item_id=int(item.id),
            expiry_policy=expiry_policy,
            shelf_life_value=(
                int(item.shelf_life_value)
                if getattr(item, "shelf_life_value", None) is not None
                else None
            ),
            shelf_life_unit=shelf_life_unit,
            lot_source_policy=lot_source_policy,
            derivation_allowed=bool(getattr(item, "derivation_allowed")),
            uom_governance_enabled=bool(getattr(item, "uom_governance_enabled")),
        )

    def _build_item_basic(self, item: Item, primary_barcode: str | None) -> ItemBasic:
        return ItemBasic(
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
            primary_barcode=(primary_barcode.strip() if isinstance(primary_barcode, str) else None),
        )
