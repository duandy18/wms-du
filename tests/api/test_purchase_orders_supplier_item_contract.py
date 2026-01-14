# tests/api/test_purchase_orders_supplier_item_contract.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest
import httpx


async def _login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    """
    项目里很多 API 都需要 Bearer token（即使某些路由没显式 Depends(get_current_user)，也可能有全局依赖）。
    这里统一走 admin 登录，保证测试稳定。
    """
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _get_items(client: httpx.AsyncClient, headers: Dict[str, str], qs: str = "") -> List[Dict[str, Any]]:
    url = f"/items{qs}"
    r = await client.get(url, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    return data


@pytest.mark.asyncio
async def test_items_filter_by_supplier_id_returns_only_supplier_items(client: httpx.AsyncClient) -> None:
    """
    合同：/items 支持 supplier_id 过滤，并返回严格子集。
    依赖：tests/fixtures/base_seed.sql 已将 (3001,3002,4002) 绑定 supplier_id=1。
    """
    headers = await _login_admin_headers(client)

    all_items = await _get_items(client, headers)
    assert len(all_items) >= 1

    s1_items = await _get_items(client, headers, "?supplier_id=1&enabled=true")
    # ✅ 至少 2 个，避免后续链路测试数据稀缺
    assert len(s1_items) >= 2

    # ✅ 返回的每个 item 都必须 supplier_id=1 且 enabled=true
    for it in s1_items:
        assert it.get("supplier_id") == 1
        assert it.get("enabled") is True


@pytest.mark.asyncio
async def test_create_po_rejects_nonexistent_item(client: httpx.AsyncClient) -> None:
    """
    合同：创建 PO 时，item_id 不存在 -> 400 且 detail 可解释。
    """
    headers = await _login_admin_headers(client)

    payload = {
        "supplier": "S1",
        "warehouse_id": 1,
        "supplier_id": 1,
        "supplier_name": "S1",
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": 9999, "qty_ordered": 1}],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 400, r.text
    assert "商品不存在" in r.json().get("detail", "")


@pytest.mark.asyncio
async def test_create_po_rejects_item_supplier_mismatch(client: httpx.AsyncClient) -> None:
    """
    合同：创建 PO 时，item.supplier_id 与 po.supplier_id 不一致 -> 400。
    使用你当前的真实样本：item_id=1 的 supplier_id=3。
    """
    headers = await _login_admin_headers(client)

    payload = {
        "supplier": "S1",
        "warehouse_id": 1,
        "supplier_id": 1,
        "supplier_name": "S1",
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": 1, "qty_ordered": 1}],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 400, r.text
    assert "不属于当前供应商" in r.json().get("detail", "")


@pytest.mark.asyncio
async def test_create_po_success_with_supplier_items(client: httpx.AsyncClient) -> None:
    """
    合同：供应商=1 且 item.supplier_id=1 的商品可以创建 PO 成功。
    我们从 /items?supplier_id=1&enabled=true 动态取一个 item_id，避免写死。
    """
    headers = await _login_admin_headers(client)

    s1_items = await _get_items(client, headers, "?supplier_id=1&enabled=true")
    assert len(s1_items) >= 1
    item_id = int(s1_items[0]["id"])

    payload = {
        "supplier": "S1",
        "warehouse_id": 1,
        "supplier_id": 1,
        "supplier_name": "S1",
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": item_id, "qty_ordered": 2}],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert data.get("supplier_id") == 1
    assert isinstance(data.get("lines"), list)
    assert len(data["lines"]) == 1
    assert int(data["lines"][0]["item_id"]) == item_id
    assert int(data["lines"][0]["qty_ordered"]) == 2
