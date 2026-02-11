# tests/api/test_platform_orders_confirm_create_contract.py
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
async def test_platform_orders_confirm_and_create_contract(client) -> None:
    """
    合同测试（最小闭环）：
    - 先 ingest 落 platform_order_lines（即使 UNRESOLVED）
    - 再 confirm-and-create 用人工决策生成内部 orders
    - 断言：返回 id/ref/manual_override/risk_flags 等关键字段存在且语义稳定
    - 幂等：重复 confirm-and-create，id 不应变化

    Phase N+4：
    - line_key 为内部幂等锚点：禁止外部输入
    - 外部定位使用 locator_kind/locator_value（或 filled_code/line_no）
    """
    token = await _login_token(client)
    headers = _auth_headers(token)

    platform = "DEMO"
    shop_id = "UT-SHOP-1"
    ext_order_no = "E2E-CONFIRM-0001"

    # 1) 先 ingest 落事实（本用例刻意构造 UNRESOLVED：缺填写码 / 填写码未绑定且不等于任何 published FSKU.code）
    ingest_payload = {
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "store_name": "UT-SHOP-1",
        "province": "广东省",
        "lines": [
            {"qty": 1, "title": "无填写码行", "spec": "颜色:黑"},
            {"filled_code": "psku:RAW-ONLY", "qty": 1, "title": "有填写码但未绑定", "spec": "颜色:黑"},
        ],
    }
    r1 = await client.post("/platform-orders/ingest", json=ingest_payload, headers=headers)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1.get("status") == "UNRESOLVED", j1
    assert j1.get("id") is None, j1
    assert isinstance(j1.get("facts_written"), int) and j1["facts_written"] >= 1, j1

    store_id = j1.get("store_id")
    assert isinstance(store_id, int) and store_id >= 1, j1

    # 2) confirm-and-create：人工指定 item_id（假设 seed baseline 中 item_id=1 存在）
    confirm_payload = {
        "platform": platform,
        "store_id": store_id,
        "ext_order_no": ext_order_no,
        "reason": "平台订单必须执行：人工按标题确认选货",
        "decisions": [
            {"locator_kind": "LINE_NO", "locator_value": "1", "item_id": 1, "qty": 1, "note": "无填写码行：人工确认为 item_id=1"},
            {"locator_kind": "FILLED_CODE", "locator_value": "psku:RAW-ONLY", "item_id": 1, "qty": 1, "note": "填写码未绑定：先救急"},
        ],
    }
    r2 = await client.post("/platform-orders/confirm-and-create", json=confirm_payload, headers=headers)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()

    assert isinstance(j2.get("status"), str) and j2["status"], j2
    assert isinstance(j2.get("id"), int) and j2["id"] > 0, j2
    assert isinstance(j2.get("ref"), str) and j2["ref"], j2
    assert j2.get("platform") == platform, j2
    assert j2.get("store_id") == store_id, j2
    assert j2.get("ext_order_no") == ext_order_no, j2

    assert j2.get("manual_override") is True, j2
    assert "manual_reason" in j2, j2

    rf = j2.get("risk_flags")
    assert isinstance(rf, list), j2
    assert "FILLED_CODE_MISSING" in rf, rf
    # current-only 语义下：有填写码但未绑定/不等于 published FSKU.code → CODE_NOT_BOUND
    assert "CODE_NOT_BOUND" in rf, rf

    first_id = int(j2["id"])

    # 3) 幂等：重复 confirm-and-create，id 不应变化
    r3 = await client.post("/platform-orders/confirm-and-create", json=confirm_payload, headers=headers)
    assert r3.status_code == 200, r3.text
    j3 = r3.json()
    assert isinstance(j3.get("id"), int) and int(j3["id"]) == first_id, j3
    assert isinstance(j3.get("status"), str) and j3["status"], j3
