from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .base import CanonicalOrder, OrderAdapter


class PddOrderAdapter(OrderAdapter):
    def normalize(self, payload: Dict[str, Any]) -> CanonicalOrder:
        # 下面字段名按你真实 PDD JSON 调整；此处给出合理默认与兜底
        platform = "PDD"
        shop_id = str(payload.get("mall_id") or payload.get("shop_id") or "UNKNOWN")
        ext_no = str(payload.get("order_sn") or payload.get("order_no") or payload.get("id"))
        occurred_at = _parse_dt(payload.get("created_at") or payload.get("order_create_time"))

        buyer_name = payload.get("receiver_name")
        buyer_phone = payload.get("receiver_phone")

        # 金额：用 pay_amount/实际支付，order_amount/应付
        order_amount = _to_f(payload.get("goods_amount") or payload.get("order_amount") or 0)
        pay_amount = _to_f(payload.get("pay_amount") or payload.get("order_amount") or 0)

        # 行项目：PDD 通常有 items/list
        lines: List[Dict[str, Any]] = []
        for row in payload.get("items", []):
            lines.append(
                {
                    "sku_id": str(row.get("sku_id") or row.get("spec_id") or ""),
                    "item_id": row.get("item_id"),
                    "title": row.get("goods_name") or row.get("title") or "",
                    "qty": int(row.get("quantity") or row.get("goods_count") or 1),
                    "price": _to_f(row.get("goods_price") or row.get("price") or 0),
                    "discount": _to_f(row.get("discount") or 0),
                    "amount": _to_f(
                        row.get("amount")
                        or (row.get("goods_price") or 0) * (row.get("quantity") or 1)
                    ),
                    "extras": {
                        k: row.get(k)
                        for k in ("goods_id", "sku_properties", "outer_sku_id")
                        if k in row
                    },
                }
            )

        # 地址
        addr = payload.get("address") or {}
        address = {
            "receiver_name": buyer_name,
            "receiver_phone": buyer_phone,
            "province": addr.get("province") or payload.get("province"),
            "city": addr.get("city"),
            "district": addr.get("district"),
            "detail": addr.get("detail") or payload.get("address_detail"),
            "zipcode": addr.get("zip") or None,
        }

        # 订单 extras（整单级）
        extras = {
            "remark": payload.get("seller_memo") or payload.get("note"),
            "flags": payload.get("flags"),
            "raw": payload.get("_raw_id") or None,  # 原始 id 备查
        }

        return CanonicalOrder(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_no,
            occurred_at=occurred_at,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            order_amount=order_amount,
            pay_amount=pay_amount,
            lines=lines,
            address=address,
            extras=extras,
        )


def _to_f(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _parse_dt(x) -> datetime:
    if isinstance(x, datetime):
        return x
    # 根据你的真实格式加解析；兜底用现在
    return datetime.utcnow()
