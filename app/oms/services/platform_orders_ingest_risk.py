# app/api/routers/platform_orders_ingest_risk.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _rank_level(level: str) -> int:
    s = str(level or "").upper().strip()
    if s == "HIGH":
        return 3
    if s == "MEDIUM":
        return 2
    if s == "LOW":
        return 1
    return 0


def _max_level(levels: List[str]) -> Optional[str]:
    if not levels:
        return None
    best = ""
    best_rank = 0
    for lv in levels:
        r = _rank_level(lv)
        if r > best_rank:
            best_rank = r
            best = str(lv).upper().strip()
    return best or None


def aggregate_risk_from_unresolved(unresolved: List[Dict[str, Any]]) -> Tuple[List[str], Optional[str], Optional[str]]:
    """
    聚合订单级风险：
    - risk_flags: 去重后的 flag 集合
    - risk_level: 取最高等级
    - risk_reason: 取第一条原因（可预期）
    """
    risk_flags: List[str] = []
    risk_levels: List[str] = []
    risk_reasons: List[str] = []

    for u in unresolved or []:
        if not isinstance(u, dict):
            continue
        rf = u.get("risk_flags")
        rl = u.get("risk_level")
        rr = u.get("risk_reason")

        if isinstance(rf, list):
            for x in rf:
                if isinstance(x, str) and x and x not in risk_flags:
                    risk_flags.append(x)

        if isinstance(rl, str) and rl.strip():
            risk_levels.append(rl.strip())

        if isinstance(rr, str) and rr.strip():
            risk_reasons.append(rr.strip())

    risk_level = _max_level(risk_levels)
    risk_reason = risk_reasons[0] if risk_reasons else None
    return risk_flags, risk_level, risk_reason
