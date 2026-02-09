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


def validate_and_build_item_qty_map(
    *,
    fact_lines: List[Dict[str, Any]],
    decisions: List[PlatformOrderManualDecisionIn],
    line_key_from_inputs,
) -> Tuple[Dict[int, int], List[Dict[str, Any]]]:
    """
    将人工决策聚合为 item_qty_map，并输出 audit_decisions（用于审计/回显）。
    最小护栏：
    - 多行订单：每条 decision 必须能定位到事实行（line_key / platform_sku_id / line_no）
    - 单行订单：允许 decision 省略定位字段（自动命中唯一事实行）
    - qty 必须 >0
    - 不强制要求“等于事实 qty”（允许拆分/部分发货），但审计里会带 fact_qty。
    """
    if not decisions:
        raise ValueError("decisions 不能为空（至少一条）")

    if not fact_lines:
        raise ValueError("未找到事实行（请先 ingest 落事实）")

    by_line_key: Dict[str, Dict[str, Any]] = {}
    for ln in fact_lines or []:
        lk = str(ln.get("line_key") or "")
        if lk:
            by_line_key[lk] = ln

    # 单行订单：预取唯一事实行 line_key（如果存在）
    single_line_key: Optional[str] = None
    if len(fact_lines) == 1:
        only = fact_lines[0] if isinstance(fact_lines[0], dict) else {}
        lk = str(only.get("line_key") or "").strip()
        if lk:
            single_line_key = lk

    item_qty_map: Dict[int, int] = {}
    audit_decisions: List[Dict[str, Any]] = []

    for d in decisions:
        psku = (d.platform_sku_id or "").strip() if d.platform_sku_id else None
        lk = (d.line_key or "").strip() if d.line_key else None

        # ✅ 单行订单：允许缺定位字段，自动命中唯一事实行
        if not lk and len(fact_lines) == 1 and single_line_key:
            lk = single_line_key

        if not lk:
            lk = line_key_from_inputs(platform_sku_id=psku, line_no=d.line_no)

        if not lk:
            raise ValueError("decision 缺少定位信息：请提供 line_key 或 platform_sku_id 或 line_no")

        fact = by_line_key.get(lk)
        if not fact:
            # 单行订单：如果事实行没有 line_key（极少见），就用唯一事实行兜底
            if len(fact_lines) == 1 and isinstance(fact_lines[0], dict):
                fact = fact_lines[0]
            else:
                raise ValueError(f"decision 未命中事实行：line_key={lk}")

        item_id = int(d.item_id)
        qty = int(d.qty)
        if qty <= 0:
            raise ValueError(f"decision.qty 必须 >0：line_key={lk}")

        item_qty_map[item_id] = int(item_qty_map.get(item_id, 0)) + qty

        audit_decisions.append(
            {
                "line_key": lk,
                "line_no": int((fact or {}).get("line_no") or 0),
                "platform_sku_id": (fact or {}).get("platform_sku_id"),
                "fact_qty": int((fact or {}).get("qty") or 1),
                "title": (fact or {}).get("title"),
                "spec": (fact or {}).get("spec"),
                "item_id": item_id,
                "qty": qty,
                "note": d.note,
            }
        )

    return item_qty_map, audit_decisions
