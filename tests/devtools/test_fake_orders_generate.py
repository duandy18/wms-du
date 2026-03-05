# tests/devtools/test_fake_orders_generate.py
from __future__ import annotations

from app.services.devtools.fake_orders_service import generate_orders, parse_seed


def test_generate_orders_includes_address_fields_for_pick_flow() -> None:
    seed = parse_seed(
        {
            "platform": "PDD",
            "shops": [
                {
                    "shop_id": "1",
                    "title_prefix": "【模拟】",
                    "links": [
                        {
                            "spu_key": "SPU-1",
                            "title": "测试商品",
                            "variants": [{"variant_name": "默认规格", "filled_code": "UT-REPLAY-FSKU-1"}],
                        }
                    ],
                }
            ],
        }
    )

    orders, stats = generate_orders(
        seed=seed,
        count=3,
        lines_min=1,
        lines_max=1,
        qty_min=1,
        qty_max=1,
        rng_seed=42,
    )

    assert stats["generated"] == 3
    assert len(orders) == 3

    # 为了“最终拿到拣货端测试”，DevTools 生成订单必须具备最小地址要素
    required_keys = {"province", "city", "district", "address"}
    for o in orders:
        missing = sorted([k for k in required_keys if not o.get(k)])
        assert not missing, f"order missing address fields: {missing}. order={o}"
