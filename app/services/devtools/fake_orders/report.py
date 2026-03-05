# app/services/devtools/fake_orders/report.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


def _collect_line_level_risk_flags(resp: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for bucket_name in ("resolved", "unresolved"):
        arr = resp.get(bucket_name) or []
        if not isinstance(arr, list):
            continue
        for row in arr:
            rf = row.get("risk_flags")
            if isinstance(rf, list):
                out.extend([str(x) for x in rf])
    return out


def _collect_next_actions_line_level(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    unresolved = resp.get("unresolved") or []
    if not isinstance(unresolved, list):
        return out
    for row in unresolved:
        na = row.get("next_actions")
        if isinstance(na, list):
            for x in na:
                if isinstance(x, dict):
                    out.append(x)
    return out


def _dedup_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for a in actions:
        action = str(a.get("action") or "")
        endpoint = str(a.get("endpoint") or "")
        payload = a.get("payload")
        key = str({"action": action, "endpoint": endpoint, "payload": payload})
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _build_ingest_line_index(resp: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for bucket in ("resolved", "unresolved"):
        arr = resp.get(bucket) or []
        if not isinstance(arr, list):
            continue
        for row in arr:
            fc = row.get("filled_code")
            if fc is None:
                continue
            idx[str(fc)] = row
    return idx


def _check_expanded_items_multiplication(order: Dict[str, Any], resp: Dict[str, Any]) -> Tuple[int, List[Dict[str, Any]]]:
    qty_map: Dict[str, List[int]] = {}
    for ln in order.get("lines") or []:
        fc = ln.get("filled_code")
        if fc is None:
            continue
        q = ln.get("qty")
        try:
            qi = int(q)
        except Exception:
            continue
        qty_map.setdefault(str(fc), []).append(qi)

    violations: List[Dict[str, Any]] = []
    resolved = resp.get("resolved") or []
    if not isinstance(resolved, list):
        return 0, violations

    for row in resolved:
        fc = row.get("filled_code")
        if fc is None:
            continue
        fc_s = str(fc)
        line_qtys = qty_map.get(fc_s) or []
        exp = row.get("expanded_items")
        if not isinstance(exp, list):
            continue
        for ei in exp:
            if not isinstance(ei, dict):
                continue
            if "need_qty" not in ei or "component_qty" not in ei:
                continue
            try:
                need = int(float(ei.get("need_qty")))
                comp = int(float(ei.get("component_qty")))
            except Exception:
                continue

            ok = False
            for q in line_qtys:
                if need == comp * q:
                    ok = True
                    break
            if not ok and line_qtys:
                violations.append(
                    {
                        "filled_code": fc_s,
                        "line_qtys": line_qtys,
                        "expanded_item": ei,
                        "reason": "need_qty != component_qty * line.qty",
                    }
                )

    return len(violations), violations[:20]


def build_report(
    *,
    orders: List[Dict[str, Any]],
    ingest_responses: List[Dict[str, Any]],
    watch_filled_codes: List[str],
    replay_responses: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    watch_set = {c for c in watch_filled_codes if c}
    report: Dict[str, Any] = {
        "items": len(orders),
        "by_status": {},
        "by_unresolved_reason": {},
        "by_risk_flag_line": {},
        "next_actions_line_level_count": 0,
        "next_actions_total_dedup_count": 0,
        "watch_filled_codes": sorted(list(watch_set)),
        "watch_stats": {},
        "expanded_items_multiplication": {"checked_orders": 0, "violations_count": 0, "violation_samples": []},
        "replay_stats": None,
    }

    for c in watch_set:
        report["watch_stats"][c] = {
            "orders_with_code": 0,
            "lines_with_code": 0,
            "resolved_lines": 0,
            "unresolved_lines": 0,
            "unresolved_reasons": {},
        }

    all_actions: List[Dict[str, Any]] = []

    for order, resp in zip(orders, ingest_responses, strict=True):
        st = str(resp.get("status") or "UNKNOWN")
        report["by_status"][st] = report["by_status"].get(st, 0) + 1

        unresolved = resp.get("unresolved") or []
        if isinstance(unresolved, list):
            for u in unresolved:
                r = u.get("reason")
                if r is not None:
                    rr = str(r)
                    report["by_unresolved_reason"][rr] = report["by_unresolved_reason"].get(rr, 0) + 1

        for f in _collect_line_level_risk_flags(resp):
            report["by_risk_flag_line"][f] = report["by_risk_flag_line"].get(f, 0) + 1

        na_line = _collect_next_actions_line_level(resp)
        report["next_actions_line_level_count"] += len(na_line)
        all_actions.extend(na_line)

        if watch_set:
            idx = _build_ingest_line_index(resp)
            order_lines = order.get("lines") or []
            if isinstance(order_lines, list):
                for code in watch_set:
                    hit_lines = [ln for ln in order_lines if ln.get("filled_code") == code]
                    if not hit_lines:
                        continue
                    ws = report["watch_stats"][code]
                    ws["orders_with_code"] += 1
                    ws["lines_with_code"] += len(hit_lines)

                    row = idx.get(code)
                    if row is None:
                        ws["unresolved_lines"] += len(hit_lines)
                        ws["unresolved_reasons"]["MISSING_IN_RESPONSE"] = (
                            ws["unresolved_reasons"].get("MISSING_IN_RESPONSE", 0) + len(hit_lines)
                        )
                    else:
                        reason = row.get("reason")
                        if reason is None:
                            ws["resolved_lines"] += len(hit_lines)
                        else:
                            ws["unresolved_lines"] += len(hit_lines)
                            rr = str(reason)
                            ws["unresolved_reasons"][rr] = ws["unresolved_reasons"].get(rr, 0) + len(hit_lines)

        vcnt, vsamples = _check_expanded_items_multiplication(order, resp)
        report["expanded_items_multiplication"]["checked_orders"] += 1
        report["expanded_items_multiplication"]["violations_count"] += vcnt
        if vsamples and len(report["expanded_items_multiplication"]["violation_samples"]) < 20:
            report["expanded_items_multiplication"]["violation_samples"].append({"ext_order_no": order.get("ext_order_no"), "samples": vsamples})
            report["expanded_items_multiplication"]["violation_samples"] = report["expanded_items_multiplication"]["violation_samples"][:20]

    report["next_actions_total_dedup_count"] = len(_dedup_actions(all_actions))

    if replay_responses is not None:
        replay_stats = {"attempted": len(replay_responses), "ok": 0, "http_errors": 0, "by_status": {}}
        for r in replay_responses:
            st = str(r.get("status") or "UNKNOWN")
            replay_stats["ok"] += 1
            replay_stats["by_status"][st] = replay_stats["by_status"].get(st, 0) + 1
        report["replay_stats"] = replay_stats

    return report
