#!/usr/bin/env python3
# scripts/dev/fake_pdd_orders.py
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import request
from urllib.error import HTTPError, URLError


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
        f.write("\n")


def _iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            yield json.loads(s)


def _append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(_json_dumps(obj))
        f.write("\n")


@dataclass(frozen=True)
class Variant:
    variant_name: str
    filled_code: str


@dataclass(frozen=True)
class Link:
    spu_key: str
    title: str
    variants: List[Variant]


@dataclass(frozen=True)
class ShopSeed:
    shop_id: str
    title_prefix: str
    links: List[Link]


@dataclass(frozen=True)
class Seed:
    platform: str
    shops: List[ShopSeed]


def _parse_seed(seed_obj: Dict[str, Any]) -> Seed:
    platform = str(seed_obj.get("platform") or "PDD")
    shops_raw = seed_obj.get("shops") or []
    shops: List[ShopSeed] = []
    for s in shops_raw:
        shop_id = str(s.get("shop_id"))
        title_prefix = str(s.get("title_prefix") or "")
        links_raw = s.get("links") or []
        links: List[Link] = []
        for lk in links_raw:
            spu_key = str(lk.get("spu_key"))
            title = str(lk.get("title") or "")
            variants_raw = lk.get("variants") or []
            if not (1 <= len(variants_raw) <= 6):
                raise ValueError(
                    f"Seed violation: link {spu_key} variants must be 1..6, got {len(variants_raw)}"
                )
            variants: List[Variant] = []
            for v in variants_raw:
                variants.append(
                    Variant(
                        variant_name=str(v.get("variant_name") or ""),
                        filled_code=str(v.get("filled_code") or ""),
                    )
                )
            links.append(Link(spu_key=spu_key, title=title, variants=variants))
        shops.append(ShopSeed(shop_id=shop_id, title_prefix=title_prefix, links=links))
    if not shops:
        raise ValueError("Seed must contain at least one shop.")
    return Seed(platform=platform, shops=shops)


def _pick_shop_link_variant(rng: random.Random, seed: Seed) -> Tuple[ShopSeed, Link, Variant]:
    shop = rng.choice(seed.shops)
    if not shop.links:
        raise ValueError(f"Shop {shop.shop_id} has no links.")
    link = rng.choice(shop.links)
    if not link.variants:
        raise ValueError(f"Link {link.spu_key} has no variants.")
    variant = rng.choice(link.variants)
    return shop, link, variant


def _make_ext_order_no(platform: str, shop_id: str, seq: int, salt: int) -> str:
    # 你后续想把 case_id 编进去也行，先保证稳定 + 不撞
    return f"FAKE-{platform}-{shop_id}-{salt}-{seq:06d}"


def generate_orders(
    seed: Seed,
    count: int,
    lines_min: int,
    lines_max: int,
    qty_min: int,
    qty_max: int,
    rng_seed: int,
    out_path: str,
) -> Dict[str, Any]:
    rng = random.Random(rng_seed)
    salt = rng.randint(1000, 9999)

    # 清空输出文件，避免追加污染
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("")

    stats: Dict[str, Any] = {
        "generated": 0,
        "rng_seed": rng_seed,
        "salt": salt,
        "out": out_path,
        "links_used": {},
        "variants_used": {},
    }

    for i in range(count):
        shop, link, _ = _pick_shop_link_variant(rng, seed)
        n_lines = rng.randint(lines_min, lines_max)
        lines: List[Dict[str, Any]] = []
        for _j in range(n_lines):
            _shop2, link2, var2 = _pick_shop_link_variant(rng, seed)
            # 强约束：同一订单的 shop_id 必须一致（真实场景如此）
            # 所以这里强制使用第一次抽到的 shop
            if _shop2.shop_id != shop.shop_id:
                # 重新抽直到 shop 一致（简单粗暴但足够）
                for _k in range(20):
                    _shop2, link2, var2 = _pick_shop_link_variant(rng, seed)
                    if _shop2.shop_id == shop.shop_id:
                        break
            qty = rng.randint(qty_min, qty_max)
            title = f"{shop.title_prefix}{link2.title}".strip() or link2.title or "【FAKE】商品"
            spec = var2.variant_name or "默认规格"
            lines.append(
                {
                    "qty": qty,
                    "filled_code": var2.filled_code,
                    "title": title,
                    "spec": spec,
                    # debug 元信息（不进后端契约也没关系，写进生成文件方便溯源）
                    "_spu_key": link2.spu_key,
                    "_variant_name": var2.variant_name,
                }
            )

            stats["links_used"][link2.spu_key] = stats["links_used"].get(link2.spu_key, 0) + 1
            stats["variants_used"][var2.filled_code] = stats["variants_used"].get(var2.filled_code, 0) + 1

        order = {
            "platform": seed.platform,
            "shop_id": shop.shop_id,
            "ext_order_no": _make_ext_order_no(seed.platform, shop.shop_id, i + 1, salt),
            "lines": lines,
        }
        _append_jsonl(out_path, order)
        stats["generated"] += 1

    return stats


def _http_post_json(url: str, payload: Dict[str, Any], token: Optional[str]) -> Tuple[int, Dict[str, Any]]:
    data = _json_dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return resp.status, {}
            return resp.status, json.loads(body)
    except HTTPError as e:
        body = e.read().decode("utf-8") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(body) if body else {"detail": str(e)}
        except Exception:
            parsed = {"detail": body or str(e)}
        return e.code, parsed
    except URLError as e:
        return 0, {"detail": f"URLError: {e}"}


def _extract_unresolved_reasons(resp: Dict[str, Any]) -> List[str]:
    unresolved = resp.get("unresolved") or []
    reasons: List[str] = []
    for u in unresolved:
        r = u.get("reason")
        if r is None:
            continue
        reasons.append(str(r))
    return reasons


def _extract_risk_flags_top(resp: Dict[str, Any]) -> List[str]:
    flags = resp.get("risk_flags") or []
    if isinstance(flags, list):
        return [str(x) for x in flags]
    return []


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


def _collect_next_actions_top(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    na = resp.get("next_actions")
    if isinstance(na, list):
        return na
    return []


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
    # 以 action + endpoint + payload 作为去重锚点（尽量稳定，不引入推导）
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for a in actions:
        action = str(a.get("action") or "")
        endpoint = str(a.get("endpoint") or "")
        payload = a.get("payload")
        key = _json_dumps({"action": action, "endpoint": endpoint, "payload": payload})
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _build_ingest_line_index(resp: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    将 ingest 的 resolved/unresolved 按 filled_code 做索引。
    注意：同一订单里可能同 filled_code 多行，后端返回也可能合并/拆分，
    所以这里用于“存在性/原因”统计，不用于严格一一映射。
    """
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


def _check_expanded_items_multiplication(
    order: Dict[str, Any],
    resp: Dict[str, Any],
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    校验：对每个 resolved 行，expanded_items 中 need_qty == component_qty * line.qty
    只在字段存在时校验；不做任何推断。
    """
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
                need = int(ei.get("need_qty"))
                comp = int(ei.get("component_qty"))
            except Exception:
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


def run_flow(
    base_url: str,
    token: Optional[str],
    in_jsonl: str,
    flow: List[str],
    report_path: str,
    save_responses_path: Optional[str],
    watch_filled_codes: List[str],
) -> Dict[str, Any]:
    ingest_url = base_url.rstrip("/") + "/platform-orders/ingest"
    confirm_url = base_url.rstrip("/") + "/platform-orders/confirm-and-create"
    replay_url = base_url.rstrip("/") + "/platform-orders/replay"

    watch_set = {c for c in watch_filled_codes if c}

    report: Dict[str, Any] = {
        "base_url": base_url,
        "flow": flow,
        "input": in_jsonl,
        "started_at_ms": _now_ms(),
        "items": 0,
        "http_errors": 0,
        "by_status": {},
        "by_unresolved_reason": {},
        "by_risk_flag_top": {},
        "by_risk_flag_line": {},
        "next_actions_top_level_count": 0,
        "next_actions_line_level_count": 0,
        "next_actions_total_dedup_count": 0,
        "watch_filled_codes": sorted(list(watch_set)),
        "watch_stats": {},
        "expanded_items_multiplication": {
            "checked_orders": 0,
            "violations_count": 0,
            "violation_samples": [],
        },
        "store_ids_seen": {},
        "replay_stats": {
            "attempted": 0,
            "ok": 0,
            "http_errors": 0,
            "by_status": {},
        },
    }

    for c in watch_set:
        report["watch_stats"][c] = {
            "orders_with_code": 0,
            "lines_with_code": 0,
            "resolved_lines": 0,
            "unresolved_lines": 0,
            "unresolved_reasons": {},
        }

    if save_responses_path:
        with open(save_responses_path, "w", encoding="utf-8") as f:
            f.write("")

    for order in _iter_jsonl(in_jsonl):
        report["items"] += 1
        ext_order_no = str(order.get("ext_order_no") or "")
        platform = str(order.get("platform") or "")

        st_ing, resp_ing = _http_post_json(ingest_url, order, token)
        if st_ing == 0 or st_ing >= 400:
            report["http_errors"] += 1

        status = str(resp_ing.get("status") or f"HTTP_{st_ing}")
        report["by_status"][status] = report["by_status"].get(status, 0) + 1

        reasons = _extract_unresolved_reasons(resp_ing)
        for r in reasons:
            report["by_unresolved_reason"][r] = report["by_unresolved_reason"].get(r, 0) + 1

        flags_top = _extract_risk_flags_top(resp_ing)
        for f_ in flags_top:
            report["by_risk_flag_top"][f_] = report["by_risk_flag_top"].get(f_, 0) + 1

        flags_line = _collect_line_level_risk_flags(resp_ing)
        for f_ in flags_line:
            report["by_risk_flag_line"][f_] = report["by_risk_flag_line"].get(f_, 0) + 1

        na_top = _collect_next_actions_top(resp_ing)
        na_line = _collect_next_actions_line_level(resp_ing)
        report["next_actions_top_level_count"] += len(na_top)
        report["next_actions_line_level_count"] += len(na_line)
        report["next_actions_total_dedup_count"] += len(_dedup_actions(na_top + na_line))

        store_id = resp_ing.get("store_id")
        if store_id is not None:
            sid = str(store_id)
            report["store_ids_seen"][sid] = report["store_ids_seen"].get(sid, 0) + 1

        if watch_set:
            ingest_idx = _build_ingest_line_index(resp_ing)
            order_lines = order.get("lines") or []
            if isinstance(order_lines, list):
                for code in watch_set:
                    hit_lines = [ln for ln in order_lines if ln.get("filled_code") == code]
                    if not hit_lines:
                        continue
                    ws = report["watch_stats"][code]
                    ws["orders_with_code"] += 1
                    ws["lines_with_code"] += len(hit_lines)

                    row = ingest_idx.get(code)
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

        vcnt, vsamples = _check_expanded_items_multiplication(order, resp_ing)
        report["expanded_items_multiplication"]["checked_orders"] += 1
        report["expanded_items_multiplication"]["violations_count"] += vcnt
        if vsamples and len(report["expanded_items_multiplication"]["violation_samples"]) < 20:
            report["expanded_items_multiplication"]["violation_samples"].extend(
                [{"ext_order_no": ext_order_no, "samples": vsamples}]
            )
            report["expanded_items_multiplication"]["violation_samples"] = report[
                "expanded_items_multiplication"
            ]["violation_samples"][:20]

        if save_responses_path:
            rec = {
                "order": order,
                "ingest": {"http_status": st_ing, "resp": resp_ing},
            }

        if "confirm" in flow:
            confirm_payload: Dict[str, Any] = {}
            if resp_ing.get("id") is not None:
                confirm_payload["id"] = resp_ing.get("id")
            if resp_ing.get("ref") is not None:
                confirm_payload["ref"] = resp_ing.get("ref")
            if not confirm_payload:
                st_cf, resp_cf = 0, {"detail": "confirm skipped: missing id/ref from ingest response"}
            else:
                st_cf, resp_cf = _http_post_json(confirm_url, confirm_payload, token)
                if st_cf == 0 or st_cf >= 400:
                    report["http_errors"] += 1

            if save_responses_path:
                rec["confirm"] = {"http_status": st_cf, "resp": resp_cf}

        if "replay" in flow:
            report["replay_stats"]["attempted"] += 1
            if store_id is None or not platform or not ext_order_no:
                st_rp, resp_rp = 0, {"detail": "replay skipped: missing platform/store_id/ext_order_no"}
            else:
                # 对齐 OpenAPI: PlatformOrderReplayIn requires platform + store_id + ext_order_no
                replay_payload = {
                    "platform": platform,
                    "store_id": store_id,
                    "ext_order_no": ext_order_no,
                }
                st_rp, resp_rp = _http_post_json(replay_url, replay_payload, token)

            if st_rp == 0 or st_rp >= 400:
                report["replay_stats"]["http_errors"] += 1
            else:
                report["replay_stats"]["ok"] += 1
                st = str(resp_rp.get("status") or f"HTTP_{st_rp}")
                report["replay_stats"]["by_status"][st] = report["replay_stats"]["by_status"].get(st, 0) + 1

            if save_responses_path:
                rec["replay"] = {"http_status": st_rp, "resp": resp_rp}

        if save_responses_path:
            _append_jsonl(save_responses_path, rec)

    report["finished_at_ms"] = _now_ms()
    _write_json(report_path, report)
    return report


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(prog="fake_pdd_orders", add_help=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate", help="Generate fake orders JSONL from seed.json")
    p_gen.add_argument("--seed", required=True, help="Seed JSON file path")
    p_gen.add_argument("--out", required=True, help="Output JSONL file path")
    p_gen.add_argument("--count", type=int, default=50, help="Number of orders")
    p_gen.add_argument("--lines-min", type=int, default=1, help="Min lines per order")
    p_gen.add_argument("--lines-max", type=int, default=3, help="Max lines per order")
    p_gen.add_argument("--qty-min", type=int, default=1, help="Min qty per line")
    p_gen.add_argument("--qty-max", type=int, default=3, help="Max qty per line")
    p_gen.add_argument("--rng-seed", type=int, default=42, help="Deterministic RNG seed")
    p_gen.add_argument("--stats-out", default="", help="Write generation stats JSON to this path (optional)")

    p_run = sub.add_parser("run", help="Run ingest/confirm/replay flow from orders JSONL")
    p_run.add_argument("--in", dest="in_jsonl", required=True, help="Input orders JSONL")
    p_run.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8000"))
    p_run.add_argument("--token", default=os.environ.get("TOKEN", ""), help="Bearer token (or set env TOKEN)")
    p_run.add_argument(
        "--flow",
        default="ingest",
        help="Comma-separated: ingest,confirm,replay (ingest is always performed)",
    )
    p_run.add_argument("--report", required=True, help="Report JSON output path")
    p_run.add_argument(
        "--save-responses",
        default="",
        help="Optional: save per-order responses as JSONL (for debugging explain/next_actions)",
    )
    p_run.add_argument(
        "--watch-filled-code",
        action="append",
        default=[],
        help="Optional: watch a filled_code for line-level stats (can be repeated). "
        "If omitted, defaults to watch UT-REPLAY-FSKU-1.",
    )

    args = p.parse_args(argv)

    if args.cmd == "generate":
        seed_obj = _load_json(args.seed)
        seed = _parse_seed(seed_obj)
        stats = generate_orders(
            seed=seed,
            count=args.count,
            lines_min=args.lines_min,
            lines_max=args.lines_max,
            qty_min=args.qty_min,
            qty_max=args.qty_max,
            rng_seed=args.rng_seed,
            out_path=args.out,
        )
        if args.stats_out:
            _write_json(args.stats_out, stats)
        print(_json_dumps({"ok": True, "stats": stats}))
        return 0

    if args.cmd == "run":
        flow_parts = [x.strip() for x in str(args.flow).split(",") if x.strip()]
        flow = [x for x in flow_parts if x in ("confirm", "replay")]
        token = args.token.strip() or None

        watch_codes: List[str] = []
        if args.watch_filled_code:
            watch_codes = [x.strip() for x in args.watch_filled_code if x and x.strip()]
        else:
            watch_codes = ["UT-REPLAY-FSKU-1"]

        run_flow(
            base_url=args.base_url,
            token=token,
            in_jsonl=args.in_jsonl,
            flow=flow,
            report_path=args.report,
            save_responses_path=(args.save_responses.strip() or None),
            watch_filled_codes=watch_codes,
        )
        print(_json_dumps({"ok": True, "report": args.report}))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
