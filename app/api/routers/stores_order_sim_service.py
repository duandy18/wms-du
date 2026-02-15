# app/api/routers/stores_order_sim_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.api.routers.platform_orders_ingest_routes import normalize_filled_code
from app.services.order_ingest_routing.normalize import normalize_province_name


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


def _norm_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).replace("\u3000", " ").strip()


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


def _pick_single_value(selected: List[Dict[str, Any]], field: str, *, label: str) -> str:
    vals = {_norm_str(x.get(field)) for x in selected}
    vals.discard("")
    if len(vals) > 1:
        raise HTTPException(status_code=422, detail=f"购物车选中行的 {label} 不一致，请先统一")
    return next(iter(vals), "")


def choose_buyer_from_cart(selected: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """
    从选中行抽取“客户信息”（用于喂给 ingest flow 的 buyer_* 字段）。
    - buyer_name ← receiver_name
    - buyer_phone ← receiver_phone
    """
    receiver_name = _pick_single_value(selected, "receiver_name", label="receiver_name")
    receiver_phone = _pick_single_value(selected, "receiver_phone", label="receiver_phone")
    return (receiver_name or None, receiver_phone or None)


def choose_address_from_cart(selected: List[Dict[str, Any]]) -> Dict[str, str] | None:
    """
    ✅ 与 OrderService.ingest(address=...) 刚性对齐：
      receiver_name / receiver_phone / province / city / district / detail / zipcode

    ✅ 同时做 normalize（单一真相）：
      province 走 normalize_province_name（优先标准全称；否则保留 routing key）
    """
    receiver_name = _pick_single_value(selected, "receiver_name", label="receiver_name")
    receiver_phone = _pick_single_value(selected, "receiver_phone", label="receiver_phone")
    province_raw = _pick_single_value(selected, "province", label="province")
    city = _pick_single_value(selected, "city", label="city")
    district = _pick_single_value(selected, "district", label="district")
    detail = _pick_single_value(selected, "detail", label="detail")
    zipcode = _pick_single_value(selected, "zipcode", label="zipcode")

    has_any = any([receiver_name, receiver_phone, province_raw, city, district, detail, zipcode])
    if not has_any:
        return None

    prov_norm = normalize_province_name(province_raw)

    # 最小强约束：姓名/省/市/详细地址/电话 必填（逼真订单 + 订单路由/解释依赖）
    if not receiver_name:
        raise HTTPException(status_code=422, detail="请在购物车填写 receiver_name（收货人）")
    if not prov_norm:
        raise HTTPException(status_code=422, detail="请在购物车填写 province（省份）")
    if not city:
        raise HTTPException(status_code=422, detail="请在购物车填写 city（城市）")
    if not detail:
        raise HTTPException(status_code=422, detail="请在购物车填写 detail（详细地址）")
    if not receiver_phone:
        raise HTTPException(status_code=422, detail="请在购物车填写 receiver_phone（收货电话）")

    out: Dict[str, str] = {
        "receiver_name": receiver_name,
        "receiver_phone": receiver_phone,
        "province": prov_norm,
        "city": city,
        "district": district,
        "detail": detail,
        "zipcode": zipcode,
    }
    return {k: v for k, v in out.items() if v}


def build_ext_order_no(*, platform: str, store_id: int, idempotency_key: Optional[str]) -> str:
    idk = (idempotency_key or "").strip()
    if idk:
        return f"SIM:{platform}:{int(store_id)}:{idk}"
    return f"SIM:{platform}:{int(store_id)}:{now_utc_ms()}"
