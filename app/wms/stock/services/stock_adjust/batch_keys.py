# app/wms/stock/services/stock_adjust/batch_keys.py
from __future__ import annotations

from typing import Optional


def norm_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    if not s or s.lower() == "none":
        return None
    return s
