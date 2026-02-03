# app/services/pick_task_commit_ship_apply_stock_details.py
from __future__ import annotations

from typing import Any, Dict, Optional


def shortage_detail(
    *,
    item_id: int,
    batch_code: Optional[str],
    available_qty: int,
    required_qty: int,
    path: str,
) -> Dict[str, Any]:
    short_qty = max(0, int(required_qty) - int(available_qty))
    return {
        "type": "shortage",
        "path": path,
        "item_id": int(item_id),
        "batch_code": batch_code,
        # ✅ 蓝皮书合同字段（必需）
        "required_qty": int(required_qty),
        "available_qty": int(available_qty),
        "short_qty": int(short_qty),
        # ✅ 兼容/同义字段（保留，便于旧用例/调试）
        "shortage_qty": int(short_qty),
        "need": int(required_qty),
        "on_hand": int(available_qty),
        "shortage": int(short_qty),
        "reason": "insufficient_stock",
    }
