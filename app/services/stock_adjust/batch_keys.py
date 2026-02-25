# app/services/stock_adjust/batch_keys.py
from __future__ import annotations

from typing import Optional


def norm_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None


def batch_key(batch_code_norm: Optional[str]) -> str:
    bc = norm_batch_code(batch_code_norm)
    return bc if bc is not None else "__NULL_BATCH__"


def lot_key(lot_id: Optional[int]) -> int:
    return int(lot_id) if lot_id is not None else 0
