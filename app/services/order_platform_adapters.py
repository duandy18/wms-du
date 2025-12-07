# app/services/order_platform_adapters.py
from __future__ import annotations

from typing import Any, Dict, List

from app.services.order_utils import parse_dt, to_float, to_int_pos


class BaseOrderAdapter:
    """
    把平台原始 payload 规范化为 ingest 可接收的参数 dict。

    输出统一结构：
      - platform, shop_id, ext_order_no, occurred_at
      - buyer_name, buyer_phone
      - order_amount, pay_amount
      - lines[ { sku_id, item_id, title, qty, price, discount, amount, extras } ]
      - address{ ... }
      - extras{ ... }
    """

    platform_name: str = "GENERIC"

    def normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        platform = self.platform_name
        shop_id = str(payload.get("shop_id") or payload.get("mall_id") or "UNKNOWN")
        ext_no = str(payload.get("order_sn") or payload.get("order_no") or payload.get("id") or "")
        occurred_at = parse_dt(payload.get("created_at") or payload.get("order_create_time"))

        buyer_name = payload.get("receiver_name") or payload.get("buyer_name")
        buyer_phone = payload.get("receiver_phone") or payload.get("buyer_phone")

        order_amount = to_float(payload.get("goods_amount") or payload.get("order_amount") or 0)
        pay_amount = to_float(payload.get("pay_amount") or payload.get("order_amount") or 0)

        src_items = payload.get("items") or payload.get("order_items") or []
        lines: List[Dict[str, Any]] = []
        for row in src_items:
            lines.append(
                {
                    "sku_id": str(
                        row.get("sku_id") or row.get("spec_id") or row.get("outer_sku_id") or ""
                    ),
                    "item_id": row.get("item_id"),
                    "title": row.get("goods_name") or row.get("title") or "",
                    "qty": to_int_pos(
                        row.get("quantity") or row.get("goods_count") or row.get("qty") or 1,
                        default=1,
                    ),
                    "price": to_float(row.get("goods_price") or row.get("price") or 0),
                    "discount": to_float(row.get("discount") or 0),
                    "amount": to_float(
                        row.get("amount")
                        or ((row.get("goods_price") or 0) * (row.get("quantity") or 1))
                    ),
                    "extras": {
                        k: row.get(k)
                        for k in (
                            "goods_id",
                            "outer_sku_id",
                            "sku_properties",
                            "asin",
                            "spu_id",
                        )
                        if k in row
                    },
                }
            )

        addr = payload.get("address") or {}
        address = {
            "receiver_name": buyer_name,
            "receiver_phone": buyer_phone,
            "province": addr.get("province") or payload.get("province"),
            "city": addr.get("city"),
            "district": addr.get("district"),
            "detail": addr.get("detail") or payload.get("address_detail"),
            "zipcode": addr.get("zip"),
        }

        extras = {
            "remark": payload.get("seller_memo") or payload.get("note"),
            "flags": payload.get("flags"),
            "raw_id": payload.get("id"),
            "channel": payload.get("channel"),
        }

        return {
            "platform": platform,
            "shop_id": shop_id,
            "ext_order_no": ext_no,
            "occurred_at": occurred_at,
            "buyer_name": buyer_name,
            "buyer_phone": buyer_phone,
            "order_amount": order_amount,
            "pay_amount": pay_amount,
            "lines": lines,
            "address": address,
            "extras": extras,
        }


class PddOrderAdapter(BaseOrderAdapter):
    platform_name = "PDD"


class TbOrderAdapter(BaseOrderAdapter):
    platform_name = "TAOBAO"


class TmallOrderAdapter(BaseOrderAdapter):
    platform_name = "TMALL"


class JdOrderAdapter(BaseOrderAdapter):
    platform_name = "JD"


class RedOrderAdapter(BaseOrderAdapter):
    platform_name = "RED"  # 小红书


class DouyinOrderAdapter(BaseOrderAdapter):
    platform_name = "DOUYIN"  # 抖音


class AmazonOrderAdapter(BaseOrderAdapter):
    platform_name = "AMAZON"


class TemuOrderAdapter(BaseOrderAdapter):
    platform_name = "TEMU"


class ShopifyOrderAdapter(BaseOrderAdapter):
    platform_name = "SHOPIFY"


class AliExpOrderAdapter(BaseOrderAdapter):
    platform_name = "ALIEXPRESS"  # 速卖通


_ADAPTERS: Dict[str, BaseOrderAdapter] = {
    "PDD": PddOrderAdapter(),
    "TAOBAO": TbOrderAdapter(),
    "TMALL": TmallOrderAdapter(),
    "JD": JdOrderAdapter(),
    "RED": RedOrderAdapter(),
    "DOUYIN": DouyinOrderAdapter(),
    "AMAZON": AmazonOrderAdapter(),
    "TEMU": TemuOrderAdapter(),
    "SHOPIFY": ShopifyOrderAdapter(),
    "ALIEXPRESS": AliExpOrderAdapter(),
}


def get_adapter(platform: str) -> BaseOrderAdapter:
    adapter = _ADAPTERS.get(platform.upper())
    if adapter is None:
        raise ValueError(f"unsupported platform: {platform!r}")
    return adapter
