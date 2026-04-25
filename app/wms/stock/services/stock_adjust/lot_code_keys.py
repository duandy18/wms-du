# app/wms/stock/services/stock_adjust/lot_code_keys.py
from __future__ import annotations

from typing import Optional


def norm_lot_code(lot_code: Optional[str]) -> Optional[str]:
    if lot_code is None:
        return None
    s = str(lot_code).strip()
    if not s or s.lower() == "none":
        return None
    return s
