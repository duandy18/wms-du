from __future__ import annotations

import re
from typing import Optional, Dict, Any

# 解析形如 "TASK:42 LOC:1 ITEM:3001 QTY:2" 的键值对（大小写不敏感）
_KV = re.compile(r"\b([A-Z]+):([-\w\.]+)\b", re.I)

def parse_barcode_kv(barcode: str) -> Dict[str, str]:
    """
    将条码字符串解析为 {KEY: value} 的字典，KEY 统一为大写。
    """
    if not isinstance(barcode, str) or not barcode:
        return {}
    return {m.group(1).upper(): m.group(2) for m in _KV.finditer(barcode)}

def try_fill_int_from_barcode(
    raw_value: Optional[int],
    field_name: str,
    tokens_obj: Any,
) -> Optional[int]:
    """
    若 Pydantic 字段当前值为空，尝试从 tokens.barcode 中解析对应整型值。
    支持 tokens 是 dict 或具有 .barcode 属性的对象。
    """
    if raw_value is not None:
        return raw_value

    # 兼容 tokens 为 Pydantic 子模型或 dict
    barcode = None
    if tokens_obj is None:
        barcode = None
    elif isinstance(tokens_obj, dict):
        barcode = tokens_obj.get("barcode")
    else:
        # 尝试 getattr
        barcode = getattr(tokens_obj, "barcode", None)

    if not isinstance(barcode, str) or not barcode:
        return raw_value

    kv = parse_barcode_kv(barcode)
    mapping = {
        "task_id": "TASK",
        "item_id": "ITEM",
        "qty": "QTY",
        "location_id": "LOC",
    }
    tag = mapping.get(field_name)
    if not tag:
        return raw_value
    if tag not in kv:
        return raw_value
    try:
        return int(kv[tag])
    except ValueError:
        return raw_value

def fallback_loc_id_from_barcode(payload_like: Any) -> Optional[int]:
    """
    在缺省时，从 payload_like 中尝试提取 LOC:xxx 作为 location_id 兜底。
    支持：payload dict（含 tokens.barcode）或带 .tokens.barcode 的对象。
    """
    barcode = None
    # 兼容 dict
    if isinstance(payload_like, dict):
        tokens = payload_like.get("tokens") or {}
        if isinstance(tokens, dict):
            barcode = tokens.get("barcode")
        else:
            barcode = getattr(tokens, "barcode", None)
    else:
        tokens = getattr(payload_like, "tokens", None)
        if tokens is None:
            barcode = None
        elif isinstance(tokens, dict):
            barcode = tokens.get("barcode")
        else:
            barcode = getattr(tokens, "barcode", None)

    if not isinstance(barcode, str) or not barcode:
        return None

    kv = parse_barcode_kv(barcode)
    if "LOC" in kv:
        try:
            return int(kv["LOC"])
        except ValueError:
            return None
    return None
