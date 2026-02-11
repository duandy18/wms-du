# app/services/devtools/fake_orders/generate.py
from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple

from app.services.devtools.fake_orders.types import FakeLink, FakeOrderAddr, FakeSeed, FakeShopSeed, FakeVariant


def _pick_shop_link_variant(rng: random.Random, seed: FakeSeed) -> Tuple[FakeShopSeed, FakeLink, FakeVariant]:
    shop = rng.choice(seed.shops)
    if not shop.links:
        raise ValueError(f"Shop {shop.shop_id} has no links.")
    link = rng.choice(shop.links)
    if not link.variants:
        raise ValueError(f"Link {link.spu_key} has no variants.")
    variant = rng.choice(link.variants)
    return shop, link, variant


def make_ext_order_no(platform: str, shop_id: str, seq: int, salt: int) -> str:
    return f"FAKE-{platform}-{shop_id}-{salt}-{seq:06d}"


def _make_fake_address_payload(*, rng: random.Random) -> Dict[str, Any]:
    # 目标：让 DevTools 生成的订单具备“履约/拣货链路可用”的最小地址要素
    candidates = [
        ("浙江省", "杭州市", "西湖区", "文一西路 1 号"),
        ("广东省", "深圳市", "南山区", "科技园 100 号"),
        ("上海市", "上海市", "浦东新区", "世纪大道 88 号"),
        ("北京市", "北京市", "朝阳区", "建国路 9 号"),
    ]
    province, city, district, detail = rng.choice(candidates)

    receiver_name = rng.choice(["张三", "李四", "王五", "赵六"])
    receiver_phone = f"13{rng.randint(0,9)}{rng.randint(10000000,99999999)}"

    # build_address(_P(order)) 很可能会读取 province/city/district/address 或 detail_address 等
    return {
        "province": province,
        "city": city,
        "district": district,
        "address": detail,
        "detail_address": detail,
        "receiver_name": receiver_name,
        "receiver_phone": receiver_phone,
        "buyer_name": receiver_name,
        "buyer_phone": receiver_phone,
    }


def _make_address_payload_from_seed(addr: FakeOrderAddr) -> Dict[str, Any]:
    # 允许空/None：用于模拟缺省导致的阻塞/风险旗标（前端不应拦截）
    detail = addr.detail
    receiver_name = addr.receiver_name
    receiver_phone = addr.receiver_phone

    payload: Dict[str, Any] = {
        "province": addr.province,
        "city": addr.city,
        "district": addr.district,
        # 订单顶层既有 address 又有 detail_address：沿用现有生成器口径
        "address": detail,
        "detail_address": detail,
        "receiver_name": receiver_name,
        "receiver_phone": receiver_phone,
        # 下游可能会用 buyer_*（与 receiver_* 保持一致）
        "buyer_name": receiver_name,
        "buyer_phone": receiver_phone,
    }
    # zipcode 不是所有链路都读，但作为真实 payload 补充保留
    if addr.zipcode is not None:
        payload["zipcode"] = addr.zipcode
    return payload


def generate_orders(
    *,
    seed: FakeSeed,
    count: int,
    lines_min: int,
    lines_max: int,
    qty_min: int,
    qty_max: int,
    rng_seed: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rng = random.Random(rng_seed)
    salt = rng.randint(1000, 9999)

    stats: Dict[str, Any] = {
        "generated": 0,
        "rng_seed": rng_seed,
        "salt": salt,
        "links_used": {},
        "variants_used": {},
    }

    orders: List[Dict[str, Any]] = []
    for i in range(count):
        shop, _link, _ = _pick_shop_link_variant(rng, seed)
        n_lines = rng.randint(lines_min, lines_max)

        lines: List[Dict[str, Any]] = []
        for _j in range(n_lines):
            _shop2, link2, var2 = _pick_shop_link_variant(rng, seed)

            # 强约束：同一订单 shop_id 一致
            if _shop2.shop_id != shop.shop_id:
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
                    "_spu_key": link2.spu_key,
                    "_variant_name": var2.variant_name,
                }
            )

            stats["links_used"][link2.spu_key] = stats["links_used"].get(link2.spu_key, 0) + 1
            stats["variants_used"][var2.filled_code] = stats["variants_used"].get(var2.filled_code, 0) + 1

        # 地址：如果 seed 指定了 order_addr，则优先使用；否则使用随机地址
        if seed.order_addr is not None:
            addr = _make_address_payload_from_seed(seed.order_addr)
        else:
            addr = _make_fake_address_payload(rng=rng)

        order = {
            "platform": seed.platform,
            "shop_id": shop.shop_id,
            "ext_order_no": make_ext_order_no(seed.platform, shop.shop_id, i + 1, salt),
            "lines": lines,
            # 关键：让履约/拣货链路有基本地址要素（默认生成 / 或用户指定）
            **addr,
        }
        orders.append(order)
        stats["generated"] += 1

    return orders, stats
