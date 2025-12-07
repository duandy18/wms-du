from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class CanonicalOrder:
    platform: str
    shop_id: str
    ext_order_no: str
    occurred_at: datetime
    buyer_name: Optional[str]
    buyer_phone: Optional[str]
    order_amount: float
    pay_amount: float
    lines: List[Dict[str, Any]]  # {sku_id,item_id,title,qty,price,discount,amount,extras}
    address: (
        Dict[str, Any] | None
    )  # {receiver_name,receiver_phone,province,city,district,detail,zipcode}
    extras: Dict[str, Any]  # 整单 extras（营销、备注、flags...）


class OrderAdapter:
    """把平台原始 payload 规范化为 CanonicalOrder。"""

    def normalize(self, payload: Dict[str, Any]) -> CanonicalOrder:  # pragma: no cover
        raise NotImplementedError
