# tests/api/test_orders_multi_platform_idempotent.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_order_payload(platform: str, shop_id: str, ext_order_no: str) -> dict:
    return {
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "order_amount": 10.0,
        "pay_amount": 10.0,
        "lines": [
            {
                "item_id": 1,
                "title": f"测试商品-{platform}-{shop_id}",
                "qty": 1,
                "price": 10.0,
                "amount": 10.0,
            }
        ],
    }


def test_orders_idempotent_on_same_platform_shop_ext_order() -> None:
    """
    同一 (platform, shop_id, ext_order_no) 重复创建订单：
    - 第一次返回 OK；
    - 第二次返回 IDEMPOTENT；
    - 且第二次返回的 id 与第一次相同（同一业务订单）。
    """
    platform = "PDD"
    shop_id = "SHOP_MULTI"
    ext_no = "EXT-IDEMPOTENT-001"

    payload = _make_order_payload(platform, shop_id, ext_no)

    # 第一次创建
    resp1 = client.post("/orders", json=payload)
    assert resp1.status_code == 200, resp1.text
    d1 = resp1.json()
    assert d1["status"] in ("OK", "IDEMPOTENT")
    assert isinstance(d1["id"], int)
    first_id = d1["id"]

    # 第二次创建，同样的 key
    resp2 = client.post("/orders", json=payload)
    assert resp2.status_code == 200, resp2.text
    d2 = resp2.json()

    # 幂等标记 / id 不变
    assert d2["status"] == "IDEMPOTENT"
    assert d2["id"] == first_id
    assert d2["ref"] == d1["ref"]


def test_orders_multi_platform_are_isolated() -> None:
    """
    不同 platform / 不同 shop_id 使用相同 ext_order_no 时，应当视为不同订单：
    - PDD / JD 同 ext_order_no → 两个独立订单；
    - 同平台不同 shop_id 同 ext_order_no → 两个独立订单。
    """
    ext_no = "EXT-MULTI-PLATFORM-001"

    # PDD / SHOP_A
    resp_pdd = client.post(
        "/orders",
        json=_make_order_payload("PDD", "SHOP_A", ext_no),
    )
    assert resp_pdd.status_code == 200, resp_pdd.text
    dp = resp_pdd.json()
    assert dp["status"] in ("OK", "IDEMPOTENT")
    id_pdd = dp["id"]

    # JD / SHOP_A（平台不同，应生成另一个订单）
    resp_jd = client.post(
        "/orders",
        json=_make_order_payload("JD", "SHOP_A", ext_no),
    )
    assert resp_jd.status_code == 200, resp_jd.text
    dj = resp_jd.json()
    assert dj["status"] in ("OK", "IDEMPOTENT")
    id_jd = dj["id"]

    assert isinstance(id_pdd, int)
    assert isinstance(id_jd, int)
    assert id_pdd != id_jd

    # PDD / SHOP_B（同平台不同店铺，同 ext_order_no，也应该是另一个订单）
    resp_pdd_b = client.post(
        "/orders",
        json=_make_order_payload("PDD", "SHOP_B", ext_no),
    )
    assert resp_pdd_b.status_code == 200, resp_pdd_b.text
    dpb = resp_pdd_b.json()
    id_pdd_b = dpb["id"]

    assert isinstance(id_pdd_b, int)
    assert id_pdd_b != id_pdd
