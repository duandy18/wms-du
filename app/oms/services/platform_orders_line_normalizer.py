# app/oms/services/platform_orders_line_normalizer.py
from __future__ import annotations

from typing import Any, Dict


def normalize_filled_code(line: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase N+2 · 输入归一层（无兼容兜底）

    规则：
    1) 只允许 filled_code（strip 后写回）
    2) platform_sku_id 不再作为别名存在：出现即报错
    3) 若 filled_code 缺失：保持缺失，由 resolver 统一给出 MISSING_FILLED_CODE
    """
    out = dict(line)

    legacy = out.get("platform_sku_id")
    if legacy is not None and str(legacy).strip():
        raise ValueError("platform_sku_id 已废弃：请使用 filled_code")

    fc = out.get("filled_code")
    if isinstance(fc, str) and fc.strip():
        out["filled_code"] = fc.strip()
        return out

    out.pop("filled_code", None)
    return out


__all__ = ["normalize_filled_code"]
