# app/services/platform_events_classify.py
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


_PAID_ALIASES = {
    "PAID",
    "PAID_OK",
    "NEW",
    "CREATED",
    "WAIT_SELLER_SEND_GOODS",
}
_CANCEL_ALIASES = {
    "CANCELED",
    "CANCELLED",
    "VOID",
    "TRADE_CLOSED",
}
_SHIPPED_ALIASES = {
    "SHIPPED",
    "DELIVERED",
    "WAIT_BUYER_CONFIRM_GOODS",
    "TRADE_FINISHED",
}


def classify(state: str) -> str:
    u = (state or "").upper()
    if u in _PAID_ALIASES:
        return "RESERVE"
    if u in _CANCEL_ALIASES:
        return "CANCEL"
    if u in _SHIPPED_ALIASES:
        return "SHIP"
    return "IGNORE"


def merge_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    acc: Dict[tuple, int] = defaultdict(int)
    for x in lines:
        key = (
            int(x["item_id"]),
            int(x["warehouse_id"]),
            str(x["batch_code"]),
        )
        acc[key] += int(x["qty"])
    return [
        {
            "item_id": k[0],
            "warehouse_id": k[1],
            "batch_code": k[2],
            "qty": q,
        }
        for k, q in acc.items()
    ]
