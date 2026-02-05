# tests/api/test_platform_sku_bindings_contract.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest


def _assert_problem_shape(obj: Dict[str, Any]) -> None:
    assert isinstance(obj, dict)
    assert "error_code" in obj
    assert "message" in obj
    assert "http_status" in obj
    assert "trace_id" in obj
    assert "context" in obj


async def _auth_headers(client) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    data = r.json()
    token = data.get("access_token")
    assert isinstance(token, str) and token, f"login response missing access_token: {data}"
    return {"Authorization": f"Bearer {token}"}


async def _pick_any_item_id(client, headers: Dict[str, str]) -> int:
    r = await client.get("/items", params={"limit": 1}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and data, "seed baseline items is empty"
    return int(data[0]["id"])


async def _create_draft_fsku(client, headers: Dict[str, str], name: str, unit_label: str = "套") -> Dict[str, Any]:
    r = await client.post("/fskus", json={"name": name, "unit_label": unit_label}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _publish_fsku_with_components(client, headers: Dict[str, str], name: str) -> Dict[str, Any]:
    item_id = await _pick_any_item_id(client, headers=headers)

    f = await _create_draft_fsku(client, headers=headers, name=name)

    r_comp = await client.post(
        f"/fskus/{f['id']}/components",
        json={"components": [{"item_id": item_id, "qty": 1, "role": "primary"}]},
        headers=headers,
    )
    assert r_comp.status_code == 200, r_comp.text

    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200, r_pub.text
    return r_pub.json()


async def _bind(
    client,
    headers: Dict[str, str],
    *,
    platform: str,
    shop_id: int,
    platform_sku_id: str,
    fsku_id: int,
    reason: str = "test",
):
    return await client.post(
        "/platform-sku-bindings",
        json={
            "platform": platform,
            "shop_id": shop_id,
            "platform_sku_id": platform_sku_id,
            "fsku_id": fsku_id,
            "reason": reason,
        },
        headers=headers,
    )


async def _current(client, headers: Dict[str, str], *, platform: str, shop_id: int, platform_sku_id: str):
    return await client.get(
        "/platform-sku-bindings/current",
        params={"platform": platform, "shop_id": shop_id, "platform_sku_id": platform_sku_id},
        headers=headers,
    )


async def _history(client, headers: Dict[str, str], *, platform: str, shop_id: int, platform_sku_id: str):
    return await client.get(
        "/platform-sku-bindings/history",
        params={
            "platform": platform,
            "shop_id": shop_id,
            "platform_sku_id": platform_sku_id,
            "limit": 50,
            "offset": 0,
        },
        headers=headers,
    )


@pytest.mark.asyncio
async def test_platform_sku_binding_requires_published_fsku(client):
    """
    红线 4：绑定必须指向 published FSKU（draft -> 409 + Problem）
    """
    headers = await _auth_headers(client)

    f = await _create_draft_fsku(client, headers=headers, name="FSKU-DRAFT-NOT-ALLOWED")
    r = await _bind(
        client,
        headers=headers,
        platform="PDD",
        shop_id=1,
        platform_sku_id="SKU-LOCK-1",
        fsku_id=f["id"],
        reason="draft",
    )

    assert r.status_code == 409, r.text
    p = r.json()
    _assert_problem_shape(p)
    assert p["http_status"] == 409


@pytest.mark.asyncio
async def test_platform_sku_binding_current_unique_and_history_grows(client):
    """
    红线 5：同 key 只能有一个 current；再次绑定应关闭旧 current 并产生历史
    """
    headers = await _auth_headers(client)

    f1 = await _publish_fsku_with_components(client, headers=headers, name="FSKU-PUB-1")
    f2 = await _publish_fsku_with_components(client, headers=headers, name="FSKU-PUB-2")

    key = {"platform": "PDD", "shop_id": 1, "platform_sku_id": "SKU-UNIQ-1"}

    r1 = await _bind(client, headers=headers, **key, fsku_id=f1["id"], reason="bind-1")
    assert r1.status_code == 201, r1.text

    cur1 = await _current(client, headers=headers, **key)
    assert cur1.status_code == 200, cur1.text
    cur1j = cur1.json()
    assert cur1j["current"]["effective_to"] is None
    assert cur1j["current"]["fsku_id"] == f1["id"]

    # 再 bind 到另一个 published fsku
    r2 = await _bind(client, headers=headers, **key, fsku_id=f2["id"], reason="bind-2")
    assert r2.status_code == 201, r2.text

    cur2 = await _current(client, headers=headers, **key)
    assert cur2.status_code == 200, cur2.text
    cur2j = cur2.json()
    assert cur2j["current"]["effective_to"] is None
    assert cur2j["current"]["fsku_id"] == f2["id"]

    hist = await _history(client, headers=headers, **key)
    assert hist.status_code == 200, hist.text
    histj = hist.json()

    items: List[Dict[str, Any]] = histj["items"]
    assert len(items) >= 2

    # current 数量必须为 1
    currents = [x for x in items if x["effective_to"] is None]
    assert len(currents) == 1
    assert currents[0]["fsku_id"] == f2["id"]

    # 至少有一条历史（effective_to 不为空）
    past = [x for x in items if x["effective_to"] is not None]
    assert len(past) >= 1
