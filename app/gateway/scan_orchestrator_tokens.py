# app/gateway/scan_orchestrator_tokens.py
from __future__ import annotations

import re
from typing import Any, Dict

# 只允许这三种 scan 模式（putaway 在 v2 中禁用）
ALLOWED_SCAN_MODES = {"receive", "pick", "count"}

# ---------------- token parsing ----------------
_TOKEN_MAP = {
    "ITM": "item_id",
    "ITEM": "item_id",
    "ITEM_ID": "item_id",
    "QTY": "qty",
    "B": "batch_code",
    "BATCH": "batch_code",
    "BATCH_CODE": "batch_code",
    "PD": "production_date",
    "MFG": "production_date",
    "EXP": "expiry_date",
    "EXPIRY": "expiry_date",
    "TLID": "task_line_id",
    "TASK_LINE_ID": "task_line_id",
    "WH": "warehouse_id",
    "WAREHOUSE": "warehouse_id",
    "WAREHOUSE_ID": "warehouse_id",
}
_TOKEN_RE = re.compile(r"([A-Za-z_]+)\s*:\s*([^\s]+)")


def parse_tokens(s: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for m in _TOKEN_RE.finditer(s or ""):
        k = _TOKEN_MAP.get(m.group(1).upper())
        v = m.group(2)
        if not k:
            continue
        if k in {"item_id", "qty", "task_line_id", "warehouse_id"}:
            try:
                out[k] = int(v)
            except Exception:
                pass
        elif k in {"production_date", "expiry_date"}:
            out[k] = v
        else:
            out[k] = v
    return out
