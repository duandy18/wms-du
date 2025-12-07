from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict

# 支持两种常见 GS1 表示：带括号 (01)(17)(10) 或紧凑 AI 序列（FNC1 分隔）
_AI_FIXED = {
    "01": 14,  # GTIN-14
    "17": 6,  # YYMMDD
}
_AI_VAR_MAX = {
    "10": 20,  # 批次（可变长，最多 20）
}


def _parse_aimed(code: str) -> Dict[str, Any]:
    """解析形如 (01)123456...(17)251231(10)BATCH 的 GS1"""
    out: Dict[str, Any] = {}
    # 提取 (AI)值块
    for m in re.finditer(r"\((\d{2})\)([^()]+)", code):
        ai, val = m.group(1), m.group(2)
        if ai == "01":
            out["gtin"] = val[: _AI_FIXED["01"]]
        elif ai == "17":
            y, mo, d = 2000 + int(val[0:2]), int(val[2:4]), int(val[4:6])
            out["expiry"] = date(y, mo, d)
        elif ai == "10":
            out["batch_code"] = val[: _AI_VAR_MAX["10"]]
    return out


def _parse_compact(code: str) -> Dict[str, Any]:
    """解析无括号紧凑串：01+14位+17+6位+10变长(+FNC1)"""
    out: Dict[str, Any] = {}
    i, n = 0, len(code)
    while i + 2 <= n:
        ai = code[i : i + 2]
        i += 2
        if ai in _AI_FIXED and i + _AI_FIXED[ai] <= n:
            val = code[i : i + _AI_FIXED[ai]]
            i += _AI_FIXED[ai]
            if ai == "01":
                out["gtin"] = val
            elif ai == "17":
                y, mo, d = 2000 + int(val[0:2]), int(val[2:4]), int(val[4:6])
                out["expiry"] = date(y, mo, d)
        elif ai in _AI_VAR_MAX:
            # 直到下一个已知 AI 或字符串末尾；FNC1 通常作为分隔，可能表现为非数字/非字母
            j = i
            while j < n and not (
                j + 2 <= n and code[j : j + 2] in _AI_FIXED.keys() | _AI_VAR_MAX.keys()
            ):
                j += 1
            out["batch_code"] = code[i:j][: _AI_VAR_MAX["10"]]
            i = j
        else:
            break
    return out


def parse_gs1(code: str) -> Dict[str, Any]:
    s = (code or "").strip()
    if not s:
        return {}
    # 快速启发：含括号或以 01 开头的数字串
    if "(" in s and ")" in s:
        return _parse_aimed(s)
    if s.startswith("01") and re.match(r"^\d{4,}$", s):
        return _parse_compact(s)
    return {}
