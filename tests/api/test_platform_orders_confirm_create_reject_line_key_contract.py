# tests/api/test_platform_orders_confirm_create_reject_line_key_contract.py
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
async def test_confirm_and_create_rejects_external_line_key_input(client) -> None:
    """
    Phase N+4 contract:
    - line_key is internal idempotency anchor
    - external input must NOT include line_key
    - reject with 422 and stable message
    """
    token = await _login_token(client)
    headers = _auth_headers(token)

    platform = "DEMO"
    shop_id = "UT-SHOP-REJ-LK-1"
    ext_order_no = "E2E-REJECT-LINE-KEY-0001"

    # 1) ingest facts (UNRESOLVED is fine)
    ingest_payload = {
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "store_name": "UT-SHOP-REJ-LK-1",
        "province": "广东省",
        "lines": [
            {"qty": 1, "title": "无填写码行", "spec": "颜色:黑"},
            {"filled_code": "psku:RAW-ONLY", "qty": 1, "title": "有填写码但找不到FSKU", "spec": "颜色:黑"},
        ],
    }
    r1 = await client.post("/platform-orders/ingest", json=ingest_payload, headers=headers)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    store_id = j1.get("store_id")
    assert isinstance(store_id, int) and store_id >= 1, j1

    # 2) confirm-and-create with forbidden line_key (must be rejected)
    confirm_payload = {
        "platform": platform,
        "store_id": store_id,
        "ext_order_no": ext_order_no,
        "reason": "UT: should reject line_key input",
        "decisions": [
            {
                "line_key": "NO_PSKU:1",
                "locator_kind": "LINE_NO",
                "locator_value": "1",
                "item_id": 1,
                "qty": 1,
                "note": "should be rejected",
            }
        ],
    }
    r2 = await client.post("/platform-orders/confirm-and-create", json=confirm_payload, headers=headers)
    assert r2.status_code == 422, r2.text
    j2 = r2.json()
    # problem payload shape is owned by make_problem; just check message contains the key hint
    msg = str(j2.get("message") or j2.get("detail") or "")
    assert "line_key" in msg
    assert "禁止" in msg or "forbid" in msg.lower()
