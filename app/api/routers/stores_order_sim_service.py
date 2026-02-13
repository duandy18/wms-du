# app/api/routers/stores_order_sim_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.api.routers.platform_orders_ingest_routes import normalize_filled_code


def now_utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def norm_row_no(v: Any) -> int:
    try:
        n = int(v)
    except Exception:
        raise HTTPException(status_code=422, detail="row_no 必须是整数（1..6）")
    if n < 1 or n > 6:
        raise HTTPException(status_code=422, detail="row_no 必须在 1..6")
    return n


def build_raw_lines_from_facts(
    *,
    merchant_items: List[Dict[str, Any]],
    cart_items: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    merchant_by_no = {int(x["row_no"]): x for x in merchant_items}
    cart_by_no = {int(x["row_no"]): x for x in cart_items}

    selected: List[Dict[str, Any]] = []
    raw_lines: List[Dict[str, Any]] = []

    for rn in range(1, 7):
        c = cart_by_no.get(rn) or {}
        if not bool(c.get("checked") or False):
            continue
        qty = int(c.get("qty") or 0)
        if qty <= 0:
            continue

        m = merchant_by_no.get(rn) or {}
        line = {
            "line_no": rn,
            "filled_code": (m.get("filled_code") or ""),
            "title": m.get("title"),
            "spec": m.get("spec"),
            "qty": qty,
        }
        selected.append(c)
        raw_lines.append(normalize_filled_code(line))

    if not raw_lines:
        raise HTTPException(status_code=422, detail="购物车为空：请选择 checked=true 且 qty>0 的行")

    return raw_lines, selected


def choose_address_from_cart(selected: List[Dict[str, Any]]) -> Dict[str, str] | None:
    provs = {str(x.get("province") or "").strip() for x in selected}
    cities = {str(x.get("city") or "").strip() for x in selected}

    provs.discard("")
    cities.discard("")

    if len(provs) > 1:
        raise HTTPException(status_code=422, detail="购物车选中行的 province 不一致，请先统一省份")
    if len(cities) > 1:
        raise HTTPException(status_code=422, detail="购物车选中行的 city 不一致，请先统一城市")

    province = next(iter(provs), "")
    city = next(iter(cities), "")

    if not province and not city:
        return None

    return {
        "province": province,
        "city": city,
        "district": "",
        "address": "",
        "name": "",
        "phone": "",
    }


def build_ext_order_no(*, platform: str, store_id: int, idempotency_key: Optional[str]) -> str:
    idk = (idempotency_key or "").strip()
    if idk:
        return f"SIM:{platform}:{int(store_id)}:{idk}"
    return f"SIM:{platform}:{int(store_id)}:{now_utc_ms()}"
