# app/services/devtools/fake_orders/seed.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.devtools.fake_orders.types import (
    FakeLink,
    FakeOrderAddr,
    FakeSeed,
    FakeShopSeed,
    FakeVariant,
)


def _as_opt_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    # 注意：这里不做 strip 后的“空转 None”，因为用户可能就是想模拟空值/缺省
    return s


def parse_seed(seed_obj: Dict[str, Any]) -> FakeSeed:
    platform = str(seed_obj.get("platform") or "PDD").strip() or "PDD"

    # 可选：order_addr（对齐 OrderAddrIn 字段）
    order_addr: Optional[FakeOrderAddr] = None
    order_addr_raw = seed_obj.get("order_addr")
    if order_addr_raw is not None:
        if not isinstance(order_addr_raw, dict):
            raise ValueError("Seed violation: order_addr must be an object.")
        order_addr = FakeOrderAddr(
            receiver_name=_as_opt_str(order_addr_raw.get("receiver_name")),
            receiver_phone=_as_opt_str(order_addr_raw.get("receiver_phone")),
            province=_as_opt_str(order_addr_raw.get("province")),
            city=_as_opt_str(order_addr_raw.get("city")),
            district=_as_opt_str(order_addr_raw.get("district")),
            detail=_as_opt_str(order_addr_raw.get("detail")),
            zipcode=_as_opt_str(order_addr_raw.get("zipcode")),
        )

    shops_raw = seed_obj.get("shops") or []
    if not isinstance(shops_raw, list):
        raise ValueError("Seed violation: shops must be a list.")

    shops: List[FakeShopSeed] = []
    for s in shops_raw:
        if not isinstance(s, dict):
            raise ValueError("Seed violation: shops[] must be objects.")

        shop_id = str(s.get("shop_id") or "").strip()
        if not shop_id:
            raise ValueError("Seed violation: shop_id is required.")

        title_prefix = str(s.get("title_prefix") or "")
        links_raw = s.get("links") or []
        if not isinstance(links_raw, list):
            raise ValueError(f"Seed violation: shop {shop_id} links must be a list.")
        if not links_raw:
            raise ValueError(f"Seed violation: shop {shop_id} must contain at least one link.")

        links: List[FakeLink] = []
        for lk in links_raw:
            if not isinstance(lk, dict):
                raise ValueError(f"Seed violation: shop {shop_id} links[] must be objects.")

            spu_key = str(lk.get("spu_key") or "").strip()
            if not spu_key:
                raise ValueError(f"Seed violation: shop {shop_id} link spu_key is required.")

            title = str(lk.get("title") or "")
            variants_raw = lk.get("variants") or []
            if not isinstance(variants_raw, list):
                raise ValueError(f"Seed violation: link {spu_key} variants must be a list.")
            if not (1 <= len(variants_raw) <= 6):
                raise ValueError(f"Seed violation: link {spu_key} variants must be 1..6, got {len(variants_raw)}")

            variants: List[FakeVariant] = []
            for v in variants_raw:
                if not isinstance(v, dict):
                    raise ValueError(f"Seed violation: link {spu_key} variants[] must be objects.")
                variant_name = str(v.get("variant_name") or "")
                filled_code = str(v.get("filled_code") or "").strip()
                if not filled_code:
                    raise ValueError(f"Seed violation: link {spu_key} variant filled_code is required.")
                variants.append(FakeVariant(variant_name=variant_name, filled_code=filled_code))

            links.append(FakeLink(spu_key=spu_key, title=title, variants=variants))

        shops.append(FakeShopSeed(shop_id=shop_id, title_prefix=title_prefix, links=links))

    if not shops:
        raise ValueError("Seed must contain at least one shop.")

    return FakeSeed(platform=platform, shops=shops, order_addr=order_addr)
