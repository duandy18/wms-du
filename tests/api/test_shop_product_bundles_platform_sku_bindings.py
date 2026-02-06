# tests/api/test_shop_product_bundles_platform_sku_bindings.py
from __future__ import annotations

from typing import Any, Dict

import pytest

# 复用 fsku 合同测试里的成熟 helper，避免重复写登录/FSKU 发布流程
from tests.api.test_fskus_contract import (  # noqa: F401
    _assert_problem_shape,
    _auth_headers,
    _create_draft_fsku,
    _pick_any_item_id,
    _replace_components,
)


async def _create_published_fsku_id(client, headers: Dict[str, str], *, name: str) -> int:
    item_id = await _pick_any_item_id(client, headers=headers)
    f = await _create_draft_fsku(client, headers=headers, name=name)

    # 写入 components：至少 1 条 primary（满足 publish 红线）
    await _replace_components(
        client,
        headers=headers,
        fsku_id=int(f["id"]),
        components=[{"item_id": item_id, "qty": 1, "role": "primary"}],
    )

    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200, r_pub.text
    data = r_pub.json()
    assert data["status"] == "published"
    return int(data["id"])


@pytest.mark.asyncio
async def test_platform_sku_bindings_xor_validation_422(client):
    """
    合同：item_id 与 fsku_id 必须二选一（且只能选一个）。
    同时提供时应 422（Problem shape）。
    """
    headers = await _auth_headers(client)

    item_id = await _pick_any_item_id(client, headers=headers)
    fsku_id = await _create_published_fsku_id(client, headers=headers, name="FSKU-BIND-XOR-TEST")

    payload = {
        "platform": "pdd",
        "shop_id": 1,
        "platform_sku_id": "PDD-SKU-XOR-TEST",
        "item_id": item_id,
        "fsku_id": fsku_id,
        "reason": "xor test",
    }

    r = await client.post("/platform-sku-bindings", json=payload, headers=headers)
    assert r.status_code == 422, r.text

    p = r.json()
    _assert_problem_shape(p)
    assert p["http_status"] == 422


@pytest.mark.asyncio
async def test_platform_sku_bindings_unbind_closes_current(client):
    """
    合同：unbind 只关闭 current（effective_to 填值），不插入新行。
    - 解绑前：current 200
    - 解绑后：current 404（Problem shape）
    - history.total >= 1
    """
    headers = await _auth_headers(client)

    item_id = await _pick_any_item_id(client, headers=headers)
    platform = "pdd"
    shop_id = 1
    platform_sku_id = "PDD-SKU-UNBIND-TEST"

    # 先绑定到 Item（单品场景）
    r_bind = await client.post(
        "/platform-sku-bindings",
        json={
            "platform": platform,
            "shop_id": shop_id,
            "platform_sku_id": platform_sku_id,
            "item_id": item_id,
            "reason": "bind item for unbind test",
        },
        headers=headers,
    )
    assert r_bind.status_code == 201, r_bind.text
    data_bind = r_bind.json()
    assert isinstance(data_bind, dict) and "current" in data_bind
    assert data_bind["current"]["platform"] == platform
    assert data_bind["current"]["shop_id"] == shop_id
    assert data_bind["current"]["platform_sku_id"] == platform_sku_id
    assert data_bind["current"]["item_id"] == item_id
    assert data_bind["current"]["fsku_id"] is None
    assert data_bind["current"]["effective_to"] is None

    # current 应可读
    r_cur1 = await client.get(
        "/platform-sku-bindings/current",
        params={"platform": platform, "shop_id": shop_id, "platform_sku_id": platform_sku_id},
        headers=headers,
    )
    assert r_cur1.status_code == 200, r_cur1.text

    # unbind
    r_unbind = await client.post(
        "/platform-sku-bindings/unbind",
        json={
            "platform": platform,
            "shop_id": shop_id,
            "platform_sku_id": platform_sku_id,
            "reason": "unbind test",
        },
        headers=headers,
    )
    assert r_unbind.status_code == 204, r_unbind.text

    # current 应 404 + Problem
    r_cur2 = await client.get(
        "/platform-sku-bindings/current",
        params={"platform": platform, "shop_id": shop_id, "platform_sku_id": platform_sku_id},
        headers=headers,
    )
    assert r_cur2.status_code == 404, r_cur2.text
    p = r_cur2.json()
    _assert_problem_shape(p)
    assert p["http_status"] == 404

    # history 应至少 1 条
    r_hist = await client.get(
        "/platform-sku-bindings/history",
        params={"platform": platform, "shop_id": shop_id, "platform_sku_id": platform_sku_id, "limit": 50, "offset": 0},
        headers=headers,
    )
    assert r_hist.status_code == 200, r_hist.text
    data_hist = r_hist.json()
    assert isinstance(data_hist, dict)
    assert data_hist["total"] >= 1
    assert isinstance(data_hist["items"], list) and data_hist["items"]
    first: Dict[str, Any] = data_hist["items"][0]
    assert first["effective_to"] is not None
