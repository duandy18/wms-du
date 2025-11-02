from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, Iterable

# 允许两种来源：
# 1) 前端直接传 {"barcode": "TASK:123 LOC:900 ITEM:3001 QTY:2"} 或只传单一字符串
# 2) 前端已拆好的 tokens: {"task": "TASK:123", "loc": "LOC:900", "item": "ITEM:3001", "qty": "QTY:2"}

PREFIXES = ("TASK:", "LOC:", "ITEM:", "QTY:")

@dataclass
class ScanContext:
    mode: str
    task_id: Optional[int] = None
    location_id: Optional[int] = None
    item_id: Optional[int] = None
    qty: Optional[int] = None
    device_id: Optional[str] = None
    operator: Optional[str] = None
    # 透传 extras（例如生产日/保质期天数，供 receive 使用）
    extras: Dict[str, Any] = None

def _split_barcode(s: str) -> Iterable[str]:
    # 允许多段以空格/逗号/分号/竖线分隔
    seps = [" ", ",", ";", "|"]
    for sep in seps:
        s = s.replace(sep, " ")
    return [tok for tok in s.split() if tok]

def _parse_token(tok: str) -> tuple[str, str] | None:
    for p in PREFIXES:
        if tok.startswith(p):
            return p[:-1].lower(), tok[len(p):]
    return None

def _coerce_int(val: Optional[str]) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except ValueError:
        return None

def extract_scan_context(payload: Dict[str, Any]) -> ScanContext:
    """
    统一把 /scan 的请求体解析成稳态上下文：
    {
      "mode": "...",
      "tokens": {"barcode": "TASK:1 LOC:900 ITEM:3001 QTY:2"}  # 或已拆好的字典
      "ctx": {"device_id":"RF01","operator":"alice"},
      "extras": {...}
    }
    """
    mode = (payload.get("mode") or "").strip().lower()
    tokens = payload.get("tokens") or {}
    ctx = payload.get("ctx") or {}
    extras = payload.get("extras") or {}

    # 1) 支持已拆/未拆两种输入
    raw_parts: list[str] = []
    if isinstance(tokens, dict):
        # 优先整串
        bc = tokens.get("barcode") or tokens.get("barcodes") or ""
        if isinstance(bc, str) and bc.strip():
            raw_parts.extend(_split_barcode(bc))
        # 也支持分别传 "task"/"loc"/"item"/"qty"
        for k in ("task", "loc", "item", "qty"):
            v = tokens.get(k)
            if isinstance(v, str) and v.strip():
                raw_parts.append(v.strip())
    elif isinstance(tokens, str):
        raw_parts.extend(_split_barcode(tokens))
    else:
        # 容忍数组形式
        if isinstance(tokens, list):
            for v in tokens:
                if isinstance(v, str) and v.strip():
                    raw_parts.extend(_split_barcode(v))

    # 2) 逐个解析
    kv: Dict[str, str] = {}
    for part in raw_parts:
        p = _parse_token(part)
        if p:
            k, v = p
            kv[k] = v  # 后者覆盖前者，便于用户重扫覆盖

    sc = ScanContext(
        mode=mode,
        task_id=_coerce_int(kv.get("task")),
        location_id=_coerce_int(kv.get("loc")),
        item_id=_coerce_int(kv.get("item")),
        qty=_coerce_int(kv.get("qty")),
        device_id=ctx.get("device_id") or ctx.get("device") or None,
        operator=ctx.get("operator") or ctx.get("user") or None,
        extras=extras,
    )
    return sc
