# app/services/platform_events_classify.py
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional


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


def _norm_bc(v: Any) -> Optional[str]:
    """
    统一归一 batch_code：
    - None / "" / "None" -> None
    - 其他字符串 -> strip 后的值
    """
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() == "none":
            return None
        return s
    s2 = str(v).strip()
    if not s2 or s2.lower() == "none":
        return None
    return s2


def merge_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并同一 (item_id, warehouse_id, batch_code) 的 qty。
    ✅ 关键：batch_code 允许 None，且绝对不能 str(None) -> "None"。
    """
    acc: Dict[tuple[int, int, str | None], int] = defaultdict(int)
    for x in lines:
        key = (
            int(x["item_id"]),
            int(x["warehouse_id"]),
            _norm_bc(x.get("batch_code")),
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
