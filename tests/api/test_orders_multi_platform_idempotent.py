# tests/api/test_orders_multi_platform_idempotent.py
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _make_ingest_payload(platform: str, store_code: str, ext_order_no: str) -> dict:
    return {
        "platform": platform,
        "store_code": store_code,
        "ext_order_no": ext_order_no,
        "receiver_name": "X",
        "receiver_phone": "000",
        "province": "UT-PROV",
        "lines": [
            {
                "title": f"测试商品-{platform}-{store_code}",
                "qty": 1,
            }
        ],
    }


def test_platform_orders_ingest_same_platform_store_ext_order_has_stable_ref(
    client: TestClient,
) -> None:
    """
    同一 (platform, store_code, ext_order_no) 重复 ingest：

    - 当前主线 /oms/platform-orders/ingest 是“接入 + 解析”入口，
      对 unresolved 输入不要求第二次返回 IDEMPOTENT；
    - 这里验证更稳定的合同：
        * 两次都应返回结构化结果；
        * ref 必须稳定一致；
        * status 允许保持 UNRESOLVED / FULFILLMENT_BLOCKED / OK / IDEMPOTENT。
    """
    platform = "PDD"
    store_code = "STORE_MULTI"
    ext_no = "EXT-IDEMPOTENT-001"

    payload = _make_ingest_payload(platform, store_code, ext_no)

    resp1 = client.post("/oms/platform-orders/ingest", json=payload)
    assert resp1.status_code == 200, resp1.text
    d1 = resp1.json()
    assert d1["status"] in ("OK", "IDEMPOTENT", "FULFILLMENT_BLOCKED", "UNRESOLVED")
    assert isinstance(d1["id"], int) or d1["id"] is None
    assert isinstance(d1["resolved"], list)
    assert isinstance(d1["unresolved"], list)
    assert isinstance(d1["facts_written"], int)

    resp2 = client.post("/oms/platform-orders/ingest", json=payload)
    assert resp2.status_code == 200, resp2.text
    d2 = resp2.json()
    assert d2["status"] in ("OK", "IDEMPOTENT", "FULFILLMENT_BLOCKED", "UNRESOLVED")
    assert isinstance(d2["id"], int) or d2["id"] is None
    assert isinstance(d2["resolved"], list)
    assert isinstance(d2["unresolved"], list)
    assert isinstance(d2["facts_written"], int)

    assert d2["ref"] == d1["ref"]


def test_platform_orders_ingest_multi_platform_are_isolated(client: TestClient) -> None:
    """
    不同 platform / 不同 store_code 使用相同 ext_order_no 时，应当视为不同业务单：

    - PDD / JD 同 ext_order_no → 两个独立 ref；
    - 同平台不同 store_code 同 ext_order_no → 两个独立 ref。
    """
    ext_no = "EXT-MULTI-PLATFORM-001"

    resp_pdd = client.post("/oms/platform-orders/ingest", json=_make_ingest_payload("PDD", "STORE_A", ext_no))
    assert resp_pdd.status_code == 200, resp_pdd.text
    dp = resp_pdd.json()
    assert dp["status"] in ("OK", "IDEMPOTENT", "FULFILLMENT_BLOCKED", "UNRESOLVED")
    ref_pdd = dp["ref"]

    resp_jd = client.post("/oms/platform-orders/ingest", json=_make_ingest_payload("JD", "STORE_A", ext_no))
    assert resp_jd.status_code == 200, resp_jd.text
    dj = resp_jd.json()
    assert dj["status"] in ("OK", "IDEMPOTENT", "FULFILLMENT_BLOCKED", "UNRESOLVED")
    ref_jd = dj["ref"]

    assert isinstance(ref_pdd, str) and ref_pdd
    assert isinstance(ref_jd, str) and ref_jd
    assert ref_pdd != ref_jd

    resp_pdd_b = client.post("/oms/platform-orders/ingest", json=_make_ingest_payload("PDD", "STORE_B", ext_no))
    assert resp_pdd_b.status_code == 200, resp_pdd_b.text
    dpb = resp_pdd_b.json()
    assert dpb["status"] in ("OK", "IDEMPOTENT", "FULFILLMENT_BLOCKED", "UNRESOLVED")
    ref_pdd_b = dpb["ref"]

    assert isinstance(ref_pdd_b, str) and ref_pdd_b
    assert ref_pdd_b != ref_pdd
