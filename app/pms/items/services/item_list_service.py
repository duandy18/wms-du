# app/pms/items/services/item_list_service.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.pms.items.contracts.item_list import (
    ItemListAttributeOut,
    ItemListBarcodeOut,
    ItemListDetailOut,
    ItemListRowOut,
    ItemListSkuCodeOut,
    ItemListUomOut,
)
from app.pms.items.repos.item_list_repo import (
    get_item_list_row_mapping,
    list_item_list_attribute_mappings,
    list_item_list_barcode_mappings,
    list_item_list_row_mappings,
    list_item_list_sku_code_mappings,
    list_item_list_uom_mappings,
)


class ItemListReadService:
    """
    PMS 商品列表页 owner 读服务。

    只负责商品列表页的摘要行与详情展开，不承载写入语义。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_rows(
        self,
        *,
        enabled: Optional[bool] = None,
        supplier_id: Optional[int] = None,
        q: Optional[str] = None,
        limit: int = 200,
    ) -> list[ItemListRowOut]:
        rows = list_item_list_row_mappings(
            self.db,
            enabled=enabled,
            supplier_id=supplier_id,
            q=q,
            limit=limit,
        )
        return [ItemListRowOut.model_validate(dict(row)) for row in rows]

    def get_detail(self, *, item_id: int) -> ItemListDetailOut | None:
        row = get_item_list_row_mapping(self.db, item_id=int(item_id))
        if row is None:
            return None

        uoms = list_item_list_uom_mappings(self.db, item_id=int(item_id))
        barcodes = list_item_list_barcode_mappings(self.db, item_id=int(item_id))
        sku_codes = list_item_list_sku_code_mappings(self.db, item_id=int(item_id))
        attributes = list_item_list_attribute_mappings(self.db, item_id=int(item_id))

        return ItemListDetailOut(
            row=ItemListRowOut.model_validate(dict(row)),
            uoms=[ItemListUomOut.model_validate(dict(x)) for x in uoms],
            barcodes=[ItemListBarcodeOut.model_validate(dict(x)) for x in barcodes],
            sku_codes=[ItemListSkuCodeOut.model_validate(dict(x)) for x in sku_codes],
            attributes=[ItemListAttributeOut.model_validate(dict(x)) for x in attributes],
        )
