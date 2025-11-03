from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, Optional


_TOKEN_PAIR = re.compile(r"\b([A-Za-z_]+)\s*:\s*([A-Za-z0-9\-\._]+)\b")


def _to_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None


def parse_barcode(barcode: str) -> Dict[str, Optional[int]]:
    """
    解析类似： "TASK:42 LOC:1 ITEM:3001 QTY:2" / "loc:1 item:3001 qty:2"
    返回统一字段：item_id, location_id, qty, task_id
    """
    out: Dict[str, Optional[int]] = {
        "item_id": None,
        "location_id": None,
        "qty": None,
        "task_id": None,
    }
    if not barcode:
        return out

    pairs = dict((k.lower(), v) for k, v in _TOKEN_PAIR.findall(barcode))

    # 映射各种变体
    if "item" in pairs:
        out["item_id"] = _to_int(pairs["item"])
    if "item_id" in pairs:
        out["item_id"] = _to_int(pairs["item_id"]) or out["item_id"]

    if "loc" in pairs:
        out["location_id"] = _to_int(pairs["loc"])
    if "location" in pairs:
        out["location_id"] = _to_int(pairs["location"]) or out["location_id"]
    if "location_id" in pairs:
        out["location_id"] = _to_int(pairs["location_id"]) or out["location_id"]

    if "qty" in pairs:
        out["qty"] = _to_int(pairs["qty"])
    if "quantity" in pairs:
        out["qty"] = _to_int(pairs["quantity"]) or out["qty"]

    if "task" in pairs:
        out["task_id"] = _to_int(pairs["task"])
    if "task_id" in pairs:
        out["task_id"] = _to_int(pairs["task_id"]) or out["task_id"]

    return out


def fill_from_barcode(payload: Dict) -> Dict:
    """
    从 payload.tokens.barcode 中回填缺失的字段（item_id/location_id/qty/task_id）。
    不会覆盖已存在的显式字段值。
    """
    if not isinstance(payload, dict):
        return payload

    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") if isinstance(tokens, dict) else None
    if not barcode:
        return payload

    parsed = parse_barcode(str(barcode))
    # 根层字段名与测试/请求保持一致
    for key_src, key_dst in [
        ("item_id", "item_id"),
        ("location_id", "location_id"),
        ("qty", "qty"),
        ("task_id", "task_id"),
    ]:
        if payload.get(key_dst) is None and parsed.get(key_src) is not None:
            payload[key_dst] = parsed[key_src]

    # tokens 里也补一份，方便后续调试
    if isinstance(tokens, dict):
        tokens.update(parsed)
        payload["tokens"] = tokens

    return payload


def make_scan_ref(device_id: Optional[str], occurred_at: datetime, location_id: Optional[int]) -> str:
    """
    统一生成 scan_ref（小写），形如：
    scan:rf01:2025-11-02T18:49:21.444082+00:00:loc:1
    """
    dev = (device_id or "device").lower()
    loc = f"loc:{location_id}" if location_id is not None else "loc:unknown"
    iso = occurred_at.astimezone(timezone.utc).isoformat()
    return f"scan:{dev}:{iso}:{loc}".lower()
