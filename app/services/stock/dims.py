# app/services/stock/dims.py
from __future__ import annotations


def norm_batch_code(batch_code: str | None) -> str | None:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None
