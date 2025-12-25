# app/services/order_reconcile_types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class OrderLineFact:
    item_id: int
    sku_id: str | None
    title: str | None
    qty_ordered: int
    qty_shipped: int
    qty_returned: int
    remaining_refundable: int


@dataclass
class OrderReconcileResult:
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    issues: List[str]
    lines: List[OrderLineFact]
