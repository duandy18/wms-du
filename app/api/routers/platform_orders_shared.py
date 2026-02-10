# app/api/routers/platform_orders_shared.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.api.routers.platform_orders_confirm_create_schemas import PlatformOrderManualDecisionIn


def collect_risk_flags_from_unresolved(unresolved: List[Dict[str, Any]]) -> List[str]:
    flags: List[str] = []
    for u in unresolved or []:
        if not isinstance(u, dict):
            continue
        rf = u.get("risk_flags")
        if isinstance(rf, list):
            for x in rf:
                if isinstance(x, str) and x and x not in flags:
                    flags.append(x)
    return flags


def build_items_payload_from_item_qty_map(
    *,
    item_qty_map: Dict[int, int],
    items_brief: Dict[int, Dict[str, Any]],
    store_id: int,
    source: str,
    extras: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    base_extras = {"source": source, "store_id": store_id}
    if extras:
        base_extras.update(extras)

    items_payload: List[Dict[str, Any]] = []
    for item_id in sorted(item_qty_map.keys()):
        need_qty = int(item_qty_map[item_id])
        brief = items_brief.get(item_id) or {}
        items_payload.append(
            {
                "item_id": int(item_id),
                "qty": need_qty,
                "sku_id": str(brief.get("sku") or ""),
                "title": str(brief.get("name") or ""),
                "extras": dict(base_extras),
            }
        )
    return items_payload


def _locator_key(kind: Optional[str], value: Optional[str]) -> Optional[str]:
    k = (kind or "").strip().upper()
    v = (value or "").strip()
    if not k or not v:
        return None
    return f"{k}:{v}"


def _normalize_locator_from_inputs(
    *,
    locator_kind: Optional[str],
    locator_value: Optional[str],
    filled_code: Optional[str],
    line_no: Optional[int],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize locator inputs for matching fact lines:
    - If locator_kind/value provided: use them (kind uppercased)
    - Else: derive from filled_code / line_no
    """
    lk = (locator_kind or "").strip().upper() or None
    lv = (locator_value or "").strip() or None
    if lk and lv:
        return lk, lv

    fc = (filled_code or "").strip() if filled_code else ""
    if fc:
        return "FILLED_CODE", fc

    if line_no is not None:
        return "LINE_NO", str(int(line_no))

    return None, None


def validate_and_build_item_qty_map(
    *,
    fact_lines: List[Dict[str, Any]],
    decisions: List[PlatformOrderManualDecisionIn],
    line_key_from_inputs,
) -> Tuple[Dict[int, int], List[Dict[str, Any]]]:
    """
    将人工决策聚合为 item_qty_map，并输出 audit_decisions（用于审计/回显）。

    Phase N+4：line_key（内部幂等锚点）与 locator（对外定位语义）分层：
    - 推荐：使用 locator_kind/locator_value（或 filled_code/line_no）定位事实行
    - 禁止：外部输入 line_key（内部幂等锚点，不属于对外契约）
    - 单行订单：允许 decision 省略定位字段（自动命中唯一事实行）
    - qty 必须 >0
    - 不强制要求“等于事实 qty”（允许拆分/部分发货），但审计里会带 fact_qty。
    """
    if not decisions:
        raise ValueError("decisions 不能为空（至少一条）")

    if not fact_lines:
        raise ValueError("未找到事实行（请先 ingest 落事实）")

    by_line_key: Dict[str, Dict[str, Any]] = {}
    by_locator: Dict[str, Dict[str, Any]] = {}

    for ln in fact_lines or []:
        if not isinstance(ln, dict):
            continue

        lk = str(ln.get("line_key") or "").strip()
        if lk:
            by_line_key[lk] = ln

        k = _locator_key(
            (ln.get("locator_kind") if isinstance(ln.get("locator_kind"), str) else None),
            (ln.get("locator_value") if isinstance(ln.get("locator_value"), str) else None),
        )
        if k:
            by_locator[k] = ln

    # 单行订单：预取唯一事实行
    single_fact: Optional[Dict[str, Any]] = None
    if len(fact_lines) == 1 and isinstance(fact_lines[0], dict):
        single_fact = fact_lines[0]

    item_qty_map: Dict[int, int] = {}
    audit_decisions: List[Dict[str, Any]] = []

    for d in decisions:
        # Phase N+2：只允许 filled_code；platform_sku_id 出现即报错
        legacy = (d.platform_sku_id or "").strip() if getattr(d, "platform_sku_id", None) else None
        if legacy:
            raise ValueError("platform_sku_id 已废弃：请使用 filled_code")

        # Phase N+4：禁止外部输入 line_key（内部幂等锚点）
        lk_in = (d.line_key or "").strip() if getattr(d, "line_key", None) else None
        if lk_in:
            raise ValueError("line_key 为内部幂等锚点，禁止外部输入：请使用 locator_kind/locator_value 或 filled_code 或 line_no")

        filled_code = (d.filled_code or "").strip() if getattr(d, "filled_code", None) else None

        loc_kind, loc_value = _normalize_locator_from_inputs(
            locator_kind=getattr(d, "locator_kind", None),
            locator_value=getattr(d, "locator_value", None),
            filled_code=filled_code,
            line_no=d.line_no,
        )
        loc_key = _locator_key(loc_kind, loc_value)

        fact: Optional[Dict[str, Any]] = None
        if loc_key and loc_key in by_locator:
            fact = by_locator[loc_key]

        # ✅ 单行订单：允许缺定位字段，自动命中唯一事实行
        if not fact and single_fact is not None and (not loc_key and not filled_code and d.line_no is None):
            fact = single_fact

        if not fact:
            # 兼容兜底：若 locator 未命中，退回用 filled_code/line_no 构造 line_key（仅内部推导）
            lk_fallback = line_key_from_inputs(filled_code=filled_code, line_no=d.line_no)
            if lk_fallback:
                fact = by_line_key.get(lk_fallback)

        if not fact:
            raise ValueError("decision 未命中事实行：请使用 locator_kind/locator_value 或 filled_code 或 line_no")

        line_key_internal = str((fact or {}).get("line_key") or "").strip() or None

        item_id = int(d.item_id)
        qty = int(d.qty)
        if qty <= 0:
            raise ValueError("decision.qty 必须 >0")

        item_qty_map[item_id] = int(item_qty_map.get(item_id, 0)) + qty

        audit_decisions.append(
            {
                "line_key": line_key_internal,
                "line_no": int((fact or {}).get("line_no") or 0),
                "locator_kind": (fact or {}).get("locator_kind"),
                "locator_value": (fact or {}).get("locator_value"),
                "filled_code": (fact or {}).get("filled_code"),
                "fact_qty": int((fact or {}).get("qty") or 1),
                "title": (fact or {}).get("title"),
                "spec": (fact or {}).get("spec"),
                "item_id": item_id,
                "qty": qty,
                "note": d.note,
            }
        )

    return item_qty_map, audit_decisions
