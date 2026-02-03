# app/services/outbound_commit_models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


def norm_batch_code(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # 防御：上游若把 None 走了 str()，会变成 "None"
        if s.lower() == "none":
            return None
        return s
    # 其它类型（比如 int）按字符串化处理，但仍做空/none 防御
    s2 = str(v).strip()
    if not s2 or s2.lower() == "none":
        return None
    return s2


def batch_key(bc: Optional[str]) -> str:
    return bc if bc is not None else "__NULL_BATCH__"


def problem_error_code_from_http_exc_detail(detail: Any) -> Optional[str]:
    if isinstance(detail, dict):
        v = detail.get("error_code")
        if isinstance(v, str) and v:
            return v
    return None


@dataclass
class ShipLine:
    item_id: int
    batch_code: Optional[str]
    qty: int
    warehouse_id: Optional[int] = None
    batch_id: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


def coerce_line(raw: Dict[str, Any] | ShipLine) -> ShipLine:
    if isinstance(raw, ShipLine):
        return raw
    return ShipLine(
        item_id=int(raw["item_id"]),
        batch_code=norm_batch_code(raw.get("batch_code")),
        qty=int(raw["qty"]),
        warehouse_id=(int(raw["warehouse_id"]) if raw.get("warehouse_id") is not None else None),
        batch_id=raw.get("batch_id"),
        meta=raw.get("meta"),
    )
