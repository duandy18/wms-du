# app/pms/items/services/item_barcode_service.py
from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.pms.items.repos.item_barcode_repo import (
    create_item_barcode,
    get_item_barcode_by_code,
    load_primary_barcodes_map as repo_load_primary_barcodes_map,
)
from app.pms.items.repos.item_uom_repo import get_base_item_uom


class ItemBarcodeService:
    """
    条码服务（主条码口径）：

    - 主条码真相：item_barcodes.is_primary = true AND active = true
    - 输出层投影：primary_barcode（以及兼容 alias barcode）
    - 写入层：创建 item 时可选写入一条主条码；后续更新主条码必须走 /item-barcodes
    - 条码绑定终态：条码必须绑定到 item_uom_id；主条码默认绑定到 base item_uom

    分层约束：
    - repo 负责查询/创建/唯一性相关持久化动作
    - service 只保留业务口径与错误语义，不直接写 select/ORM 细节
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _normalize_symbology(v: str | None) -> str:
        s = (v or "").strip().upper()
        return s or "CUSTOM"

    def _require_base_item_uom_id(self, *, item_id: int) -> int:
        base = get_base_item_uom(self.db, int(item_id))
        if base is None:
            raise ValueError(f"base item_uom missing for item_id={int(item_id)}")
        return int(base.id)

    def load_primary_barcodes_map(self, *, item_ids: List[int]) -> dict[int, str]:
        return repo_load_primary_barcodes_map(self.db, item_ids=item_ids)

    def ensure_unique_or_raise(self, *, barcode: str) -> None:
        code = (barcode or "").strip()
        if not code:
            raise ValueError("barcode is required")

        existing = get_item_barcode_by_code(self.db, barcode=code)
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

        create_item_barcode(
            self.db,
            item_id=int(item_id),
            item_uom_id=int(base_uom_id),
            barcode=code,
            symbology=self._normalize_symbology(symbology),
            active=True,
            is_primary=True,
        )
