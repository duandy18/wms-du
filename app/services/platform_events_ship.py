# app/services/platform_events_ship.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.platform_events_classify import merge_lines


def _norm_bc(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.lower() == "none":
            return None
        return s
    s2 = str(v).strip()
    if not s2 or s2.lower() == "none":
        return None
    return s2


def _has_all_ship_keys(arr: object) -> bool:
    if not arr:
        return False
    required_keys = {"item_id", "warehouse_id", "batch_code", "qty"}
    return all(required_keys.issubset(x.keys()) for x in arr)  # type: ignore[arg-type]


def build_ship_lines_for_commit(
    *,
    raw_event: Dict[str, Any],
    mapped: Any,
    task: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    纯函数：从 raw/mapped/task 中选出“最可信”的 ship lines，并做规范化：
    - batch_code 保留 None（不能 str(None)->"None"）
    - 必须包含 item_id/warehouse_id/batch_code/qty
    - 最终按 (item,wh,batch) 合并
    """
    raw_lines = raw_event.get("lines") or []

    mapped_ship = None
    if isinstance(mapped, dict):
        mapped_ship = mapped.get("ship_lines")

    mapped_lines = mapped.get("lines") if isinstance(mapped, dict) else None

    chosen = raw_lines if _has_all_ship_keys(raw_lines) else (mapped_ship or mapped_lines or task.get("lines") or [])

    lines = [
        {
            "item_id": int(x["item_id"]),
            "warehouse_id": int(x["warehouse_id"]),
            "batch_code": _norm_bc(x.get("batch_code")),
            "qty": int(x["qty"]),
        }
        for x in chosen
        if {"item_id", "warehouse_id", "batch_code", "qty"}.issubset(x.keys())
    ]
    if not lines:
        raise ValueError("No valid ship lines (need item_id, warehouse_id, batch_code, qty)")

    return merge_lines(lines)
