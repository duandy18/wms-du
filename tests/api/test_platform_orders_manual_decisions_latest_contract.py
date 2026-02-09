# tests/api/test_platform_orders_manual_decisions_latest_contract.py
from __future__ import annotations

from typing import Dict

import pytest


async def _login_token(client) -> str:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    j = r.json()
    tok = j.get("access_token")
    assert isinstance(tok, str) and tok, j
    return tok


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_platform_orders_manual_decisions_latest_contract(client) -> None:
    """
    合同测试：
    - 先用 shop_id 路径 ingest 落事实（UNRESOLVED）
    - 再 confirm-and-create 生成人工救火 orders（manual_override=true 写入 extras）
    - 再调用 manual-decisions/latest，能查回这笔证据
    """
    token = await _login_token(client)
    headers = _auth_headers(token)

    platform = "DEMO"
    shop_id = "UT-SHOP-MD-1"
    ext_order_no = "E2E-MD-0001"

    # 1) ingest 落事实
    ingest_payload = {
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "store_name": "UT-SHOP-MD-1",
        "province": "广东省",
        "lines": [
            {"qty": 1, "title": "无PSKU行", "spec": "颜色:黑"},
            {"platform_sku_id": "psku:RAW-ONLY", "qty": 1, "title": "有PSKU但未绑", "spec": "颜色:黑"},
        ],
    }
    r1 = await client.post("/platform-orders/ingest", json=ingest_payload, headers=headers)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1.get("status") == "UNRESOLVED", j1
    store_id = j1.get("store_id")
    assert isinstance(store_id, int) and store_id >= 1, j1

    # 2) confirm-and-create
    confirm_payload = {
        "platform": platform,
        "store_id": store_id,
        "ext_order_no": ext_order_no,
        "reason": "救火：人工按标题确认",
        "decisions": [
            {"line_key": "NO_PSKU:1", "item_id": 1, "qty": 1, "note": "无PSKU行：人工确认为 item_id=1"},
            {"line_key": "PSKU:psku:RAW-ONLY", "item_id": 1, "qty": 1, "note": "该PSKU未绑：先救急"},
        ],
    }
    r2 = await client.post("/platform-orders/confirm-and-create", json=confirm_payload, headers=headers)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert isinstance(j2.get("id"), int) and j2["id"] > 0, j2

    # 3) 查询 manual decisions
    r3 = await client.get(
        f"/platform-orders/manual-decisions/latest?platform={platform}&store_id={store_id}&limit=20&offset=0",
        headers=headers,
    )
    assert r3.status_code == 200, r3.text
    j3 = r3.json()

    assert isinstance(j3.get("items"), list), j3
    assert isinstance(j3.get("total"), int), j3

    # 至少能查到我们刚创建的那笔 ext_order_no
    hits = [x for x in j3["items"] if isinstance(x, dict) and x.get("ext_order_no") == ext_order_no]
    assert hits, j3

    one = hits[0]
    assert one.get("platform") == platform, one
    assert one.get("store_id") == store_id, one
    assert one.get("manual_decisions") and isinstance(one.get("manual_decisions"), list), one
    assert isinstance(one.get("risk_flags"), list), one
