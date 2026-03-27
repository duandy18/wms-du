# app/services/platform_order_ingest_evidence.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _first_unresolved_reason(unresolved: List[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """
    尝试从 unresolved 里提取一个稳定主因：
    返回 (reason_code, filled_code?)。
    """
    for u in unresolved or []:
        if not isinstance(u, dict):
            continue
        # 常见字段兜底：reason_code / error_code / code / reason / message
        rc = _as_str(u.get("reason_code") or u.get("error_code") or u.get("code") or u.get("reason")).strip()
        msg = _as_str(u.get("message")).strip()
        filled = _as_str(u.get("filled_code") or u.get("merchant_code") or u.get("locator_value")).strip() or None
        if rc:
            return rc, filled
        if msg:
            # 如果没有标准码，只能降级
            return "UNRESOLVED", filled
    return "UNRESOLVED", None


def derive_reason_code(out_dict: Mapping[str, Any]) -> str:
    status = _as_str(out_dict.get("status") or "").upper()
    unresolved = out_dict.get("unresolved")
    blocked_reasons = out_dict.get("blocked_reasons")
    fulfillment_status = _as_str(out_dict.get("fulfillment_status") or "")

    if status == "UNRESOLVED":
        if isinstance(unresolved, list) and len(unresolved) > 0:
            rc, _ = _first_unresolved_reason(unresolved)
            # 统一收敛到我们宪法里的主码（可逐步扩展）
            if rc in {"MISSING_FILLED_CODE", "FILLED_CODE_MISSING"}:
                return "MISSING_FILLED_CODE"
            if rc in {"CODE_NOT_BOUND", "FILLED_CODE_NOT_BOUND"}:
                return "CODE_NOT_BOUND"
            if rc in {"FSKU_NOT_FOUND"}:
                return "FSKU_NOT_FOUND"
            return rc
        return "UNRESOLVED"

    # OK 但被履约阻断
    if fulfillment_status == "FULFILLMENT_BLOCKED":
        return "ROUTING_BLOCKED"
    if isinstance(blocked_reasons, list) and len(blocked_reasons) > 0:
        return "ROUTING_BLOCKED"

    if status == "OK":
        return "OK"

    if status:
        return status

    return "INTERNAL_ERROR"


def derive_next_actions(out_dict: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """
    next_actions：面向操作者的可执行建议（先做核心 5 种，逐步扩展）
    """
    actions: List[Dict[str, Any]] = []
    platform = _as_str(out_dict.get("platform") or out_dict.get("plat") or "").strip() or None
    shop_id = _as_str(out_dict.get("shop_id") or "").strip() or None
    store_id = out_dict.get("store_id")

    reason_code = derive_reason_code(out_dict)
    unresolved = out_dict.get("unresolved") if isinstance(out_dict.get("unresolved"), list) else []
    _, filled = _first_unresolved_reason(unresolved) if isinstance(unresolved, list) else ("", None)

    if reason_code == "MISSING_FILLED_CODE":
        actions.append(
            {
                "action": "fill_filled_code",
                "label": "补填写码（filled_code）",
                "target": "merchant_lines",
                "params": {"store_id": store_id},
            }
        )

    if reason_code == "CODE_NOT_BOUND":
        actions.append(
            {
                "action": "bind_merchant_code",
                "label": "去绑定填写码 → FSKU",
                "target": "merchant_code_bindings",
                "params": {"platform": platform, "shop_id": shop_id, "store_id": store_id, "filled_code": filled},
            }
        )

    if reason_code == "FSKU_NOT_FOUND":
        actions.append(
            {
                "action": "create_fsku",
                "label": "创建/检查 FSKU",
                "target": "fsku_workbench",
                "params": {"store_id": store_id, "filled_code": filled},
            }
        )

    if reason_code == "ROUTING_BLOCKED":
        actions.append(
            {
                "action": "check_fulfillment_debug",
                "label": "查看履约阻断原因",
                "target": "orders_fulfillment_debug",
                "params": {"store_id": store_id, "ref": out_dict.get("ref")},
            }
        )

    # 默认兜底：重试
    if reason_code not in {"OK"}:
        actions.append(
            {
                "action": "retry",
                "label": "重试（确认输入后再次执行）",
                "target": "retry",
                "params": {"store_id": store_id},
            }
        )

    # 去掉 params 里 None
    for a in actions:
        p = a.get("params")
        if isinstance(p, dict):
            a["params"] = {k: v for k, v in p.items() if v is not None}

    return actions


def attach_reason_and_actions(out_dict: Dict[str, Any], *, platform: str, shop_id: str) -> Dict[str, Any]:
    """
    在 Flow 输出最后一步挂载 Phase D 字段。
    注意：platform_orders/ingest 的 response_model 若严格，会丢弃 extra 字段；
    但 order-sim/preview 返回的是 dict，不会丢。
    后续如需在 ingest API 里稳定输出，需要把 schema 也补齐。
    """
    out = dict(out_dict)
    out.setdefault("platform", platform)
    out.setdefault("shop_id", shop_id)

    out["reason_code"] = derive_reason_code(out)
    out["next_actions"] = derive_next_actions(out)
    return out
