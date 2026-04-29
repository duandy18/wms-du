# app/pms/items/services/item_presenter.py
from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.services.item_barcode_service import ItemBarcodeService
from app.pms.items.services.item_rules import decorate_rules


class ItemPresenter:
    """
    输出投影层（Presentation / Projection）：

    - 负责把“裸 Item ORM”变成“对外契约 Item”：
      * decorate_rules（requires_batch / requires_dates 等规则投影）
      * primary_barcode（主条码真相）
    - 不负责 CRUD / 事务
    - item_test_sets / is_test 已退役，不再投影测试集合字段。
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._barcodes = ItemBarcodeService(db)

    def present_items(self, *, items: List[Item]) -> List[Item]:
        if not items:
            return items

        rows = [decorate_rules(r) for r in items]

        m = self._barcodes.load_primary_barcodes_map(item_ids=[int(x.id) for x in rows])
        for it in rows:
            pb = m.get(int(it.id))
            # ✅ 只写 primary_barcode；Item.barcode property 会读取它作为兼容输出
            setattr(it, "primary_barcode", pb)

        return rows

    def present_item(self, *, item: Item | None) -> Item | None:
        if item is None:
            return None

        obj = decorate_rules(item)
        m = self._barcodes.load_primary_barcodes_map(item_ids=[int(obj.id)])
        setattr(obj, "primary_barcode", m.get(int(obj.id)))
        return obj
