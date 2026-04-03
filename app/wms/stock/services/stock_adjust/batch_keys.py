# app/wms/stock/services/stock_adjust/batch_keys.py
from __future__ import annotations

from typing import Optional


def norm_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    # 防御：不允许空串；上游若传入 "None" 也归一为 None
    if not s or s.lower() == "none":
        return None
    return s


def batch_key(batch_code_norm: Optional[str]) -> str:
    """
    Phase M-5:
    - 禁止 "__NULL_BATCH__" sentinel。
    - 仅用于内存聚合键：用空串 "" 表示 None 槽位（真实 batch_code 经 norm 后不会是空串）。
    """
    bc = norm_batch_code(batch_code_norm)
    return bc if bc is not None else ""


def lot_key(lot_id: Optional[int]) -> Optional[int]:
    """
    Phase M-5:
    - 禁止 lot_id_key=0 sentinel。
    - 内存键直接用 Optional[int]（None 就是 None）。
    """
    return int(lot_id) if lot_id is not None else None
