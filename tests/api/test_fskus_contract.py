# tests/api/test_fskus_contract.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest


def _assert_problem_shape(obj: Dict[str, Any]) -> None:
    # main.py 的 handler 会把 HTTPException.detail 统一成 Problem
    assert isinstance(obj, dict)
    assert "error_code" in obj
    assert "message" in obj
    assert "http_status" in obj
    assert "trace_id" in obj
    assert "context" in obj


async def _auth_headers(client) -> Dict[str, str]:
    """
    测试环境 baseline seed 应该包含 admin/admin123。
    拿到 access_token 后统一用于 Authorization header。
    """
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    data = r.json()
    token = data.get("access_token")
    assert isinstance(token, str) and token, f"login response missing access_token: {data}"
    return {"Authorization": f"Bearer {token}"}


async def _pick_any_item_id(client, headers: Dict[str, str]) -> int:
    # 你们 seed baseline 一定会有 items；这里用 API 取一个，避免硬编码 1
    r = await client.get("/items", params={"limit": 1}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and data, "seed baseline items is empty"
    item_id = int(data[0]["id"])
    assert item_id >= 1
    return item_id


async def _create_draft_fsku(
    client,
    headers: Dict[str, str],
    name: str = "FSKU-TEST",
    unit_label: str = "套",
) -> Dict[str, Any]:
    r = await client.post("/fskus", json={"name": name, "unit_label": unit_label}, headers=headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "draft"
    assert isinstance(data.get("id"), int)
    return data


async def _replace_components(client, headers: Dict[str, str], fsku_id: int, components: List[dict]) -> Dict[str, Any]:
    r = await client.post(
        f"/fskus/{fsku_id}/components",
        json={"components": components},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_fsku_routes_require_auth(client):
    """
    权限闸门：未携带 token 时，新接口应拒绝（401/403）。
    不强依赖错误形状（不同 get_current_user 实现可能不同），但如果返回是 Problem dict，则校验字段。
    """
    r = await client.get("/fskus")
    assert r.status_code in (401, 403), r.text

    try:
        body = r.json()
    except Exception:
        body = None

    if isinstance(body, dict) and "error_code" in body:
        _assert_problem_shape(body)


@pytest.mark.asyncio
async def test_fsku_publish_requires_components(client):
    """
    红线 1：空 components 不能 publish（409 + Problem shape）
    """
    headers = await _auth_headers(client)
    f = await _create_draft_fsku(client, headers=headers)

    r = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r.status_code == 409, r.text

    p = r.json()
    _assert_problem_shape(p)
    assert isinstance(p["message"], str) and p["message"]
    assert p["http_status"] == 409


@pytest.mark.asyncio
async def test_fsku_components_immutable_after_publish(client):
    """
    红线 2：发布后 components 冻结（再次写入应 409 + Problem）
    """
    headers = await _auth_headers(client)

    item_id = await _pick_any_item_id(client, headers=headers)
    f = await _create_draft_fsku(client, headers=headers)

    await _replace_components(
        client,
        headers=headers,
        fsku_id=f["id"],
        components=[{"item_id": item_id, "qty": 2, "role": "primary"}],
    )

    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200, r_pub.text
    data_pub = r_pub.json()
    assert data_pub["status"] == "published"

    # 再次写 components -> 409
    r2 = await client.post(
        f"/fskus/{f['id']}/components",
        json={"components": [{"item_id": item_id, "qty": 3, "role": "primary"}]},
        headers=headers,
    )
    assert r2.status_code == 409, r2.text

    p = r2.json()
    _assert_problem_shape(p)
    assert isinstance(p["message"], str) and p["message"]
    assert p["http_status"] == 409


@pytest.mark.asyncio
async def test_problem_shape_on_validation_error(client):
    """
    红线 3：422 也必须是 Problem shape（不允许 pydantic 默认 errors() 结构直出）
    """
    headers = await _auth_headers(client)

    r = await client.post("/fskus", json={"name": "", "unit_label": "套"}, headers=headers)
    assert r.status_code == 422, r.text

    p = r.json()
    _assert_problem_shape(p)
    assert p["http_status"] == 422
