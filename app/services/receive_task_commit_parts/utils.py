# app/services/receive_task_commit_parts/utils.py
from __future__ import annotations

from typing import Optional


def safe_upc(v: Optional[int]) -> int:
    try:
        n = int(v or 1)
    except Exception:
        n = 1
    return n if n > 0 else 1


def norm_optional_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def batch_key_for_touched(bc: Optional[str]) -> str:
    # 对齐 DB 的 batch_code_key 语义：COALESCE(batch_code,'__NULL_BATCH__')
    return bc if bc is not None else "__NULL_BATCH__"
