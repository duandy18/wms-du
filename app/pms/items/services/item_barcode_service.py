# app/pms/items/services/item_barcode_service.py
from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.item_barcode import ItemBarcode
from app.models.item_uom import ItemUOM


class ItemBarcodeService:
    """
    条码服务（主条码口径）：

    - 主条码真相：item_barcodes.is_primary = true AND active = true
    - 输出层投影：primary_barcode（以及兼容 alias barcode）
    - 写入层：创建 item 时可选写入一条主条码；后续更新主条码必须走 /item-barcodes
    - 条码绑定终态：条码必须绑定到 item_uom_id；主条码默认绑定到 base item_uom
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _normalize_symbology(v: str | None) -> str:
        s = (v or "").strip().upper()
        return s or "CUSTOM"

    def _require_base_item_uom_id(self, *, item_id: int) -> int:
        row = self.db.execute(
            select(ItemUOM.id)
            .where(ItemUOM.item_id == int(item_id))
            .where(ItemUOM.is_base.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError(f"base item_uom missing for item_id={int(item_id)}")
        return int(row)

    def load_primary_barcodes_map(self, *, item_ids: List[int]) -> dict[int, str]:
        ids = sorted({int(x) for x in item_ids if x is not None})
        if not ids:
            return {}

        rows = (
            self.db.execute(
                select(ItemBarcode.item_id, ItemBarcode.barcode)
                .where(ItemBarcode.item_id.in_(ids))
                .where(ItemBarcode.is_primary.is_(True))
                .where(ItemBarcode.active.is_(True))
            )
            .all()
        )
        m: dict[int, str] = {}
        for item_id, barcode in rows:
            if item_id is None or barcode is None:
                continue
            m[int(item_id)] = str(barcode)
        return m

    def ensure_unique_or_raise(self, *, barcode: str) -> None:
        code = (barcode or "").strip()
        if not code:
            raise ValueError("barcode is required")
        existing = (
            self.db.execute(select(ItemBarcode).where(ItemBarcode.barcode == code))
            .scalars()
            .first()
        )
        if existing is not None:
            raise ValueError("barcode duplicate: already bound to an item")

    def create_primary_for_item(
        self,
        *,
        item_id: int,
        barcode: str,
        symbology: str = "EAN13",
    ) -> None:
        code = (barcode or "").strip()
        if not code:
            return
        self.ensure_unique_or_raise(barcode=code)

        base_uom_id = self._require_base_item_uom_id(item_id=int(item_id))

        b = ItemBarcode(
            item_id=int(item_id),
            item_uom_id=int(base_uom_id),
            barcode=code,
            symbology=self._normalize_symbology(symbology),
            active=True,
            is_primary=True,
        )
        self.db.add(b)
