# app/services/item_presenter.py
from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.item import Item
from app.services.item_barcode_service import ItemBarcodeService
from app.services.item_rules import decorate_rules
from app.services.item_test_set_service import ItemTestSetService


class ItemPresenter:
    """
    输出投影层（Presentation / Projection）：

    - 负责把“裸 Item ORM”变成“对外契约 Item”：
      * decorate_rules（requires_batch / default_batch_code 等规则投影）
      * is_test（DEFAULT test set membership）
      * primary_barcode（主条码真相）
    - 不负责 CRUD / 事务
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._test_sets = ItemTestSetService(db)
        self._barcodes = ItemBarcodeService(db)

    def present_items(self, *, items: List[Item]) -> List[Item]:
        if not items:
            return items

        rows = [decorate_rules(r) for r in items]
        rows = self._test_sets.attach_is_test_for_items(items=rows, set_code="DEFAULT")

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
        obj = self._test_sets.attach_is_test_for_item(item=obj, set_code="DEFAULT")
        assert obj is not None

        m = self._barcodes.load_primary_barcodes_map(item_ids=[int(obj.id)])
        setattr(obj, "primary_barcode", m.get(int(obj.id)))
        return obj
