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


async def _pick_two_item_ids(client, headers: Dict[str, str]) -> tuple[int, int]:
    r = await client.get("/items", params={"limit": 2}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and len(data) >= 2, "seed baseline items must have at least 2 rows"
    a = int(data[0]["id"])
    b = int(data[1]["id"])
    assert a >= 1 and b >= 1 and a != b
    return a, b


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


async def _post_replace_components(client, headers: Dict[str, str], fsku_id: int, components: List[dict]):
    return await client.post(
        f"/fskus/{fsku_id}/components",
        json={"components": components},
        headers=headers,
    )


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
async def test_fsku_list_contract_shape(client):
    """
    合同：GET /fskus 返回分页 envelope（items/total/limit/offset），且 items 的字段集合固定。
    这个测试用于保证前端可以“刚性解包”，避免出现把 dict 当 list 用的灾难。
    """
    headers = await _auth_headers(client)

    r = await client.get("/fskus", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert isinstance(data, dict), data

    assert "items" in data and isinstance(data["items"], list)
    assert "total" in data and isinstance(data["total"], int)
    assert "limit" in data and isinstance(data["limit"], int)
    assert "offset" in data and isinstance(data["offset"], int)

    # items 允许为空；非空时校验字段 shape
    items = data["items"]
    if items:
        one = items[0]
        assert isinstance(one, dict), one

        # 必备字段（与前端对齐）
        for k in ("id", "name", "unit_label", "status", "updated_at"):
            assert k in one, one

        assert isinstance(one["id"], int)
        assert isinstance(one["name"], str)
        assert isinstance(one["unit_label"], str)
        assert one["status"] in ("draft", "published", "retired")
        assert isinstance(one["updated_at"], str) and one["updated_at"]


@pytest.mark.asyncio
async def test_fsku_components_read_contract_shape(client):
    """
    合同：必须可读 components。
    - GET /fskus/{id}/components -> 200
    - 返回体包含 components: list
    - publish 后仍可读（只冻结写）
    """
    headers = await _auth_headers(client)

    item_id = await _pick_any_item_id(client, headers=headers)
    f = await _create_draft_fsku(client, headers=headers)

    # 写入 components
    await _replace_components(
        client,
        headers=headers,
        fsku_id=f["id"],
        components=[{"item_id": item_id, "qty": 2, "role": "primary"}],
    )

    # 读 components（新的 GET endpoint）
    r_get = await client.get(f"/fskus/{f['id']}/components", headers=headers)
    assert r_get.status_code == 200, r_get.text
    body = r_get.json()
    assert isinstance(body, dict), body
    assert "components" in body and isinstance(body["components"], list)

    comps = body["components"]
    assert len(comps) >= 1
    c0 = comps[0]
    assert isinstance(c0, dict), c0
    for k in ("item_id", "qty", "role"):
        assert k in c0, c0
    assert isinstance(c0["item_id"], int)
    assert isinstance(c0["qty"], int)
    assert c0["role"] in ("primary", "gift")

    # publish 后仍应可读
    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200, r_pub.text

    r_get2 = await client.get(f"/fskus/{f['id']}/components", headers=headers)
    assert r_get2.status_code == 200, r_get2.text
    body2 = r_get2.json()
    assert "components" in body2 and isinstance(body2["components"], list)


@pytest.mark.asyncio
async def test_fsku_components_support_gift_role(client):
    """
    Phase A 合同：components.role 支持 primary/gift，且可写可读。
    """
    headers = await _auth_headers(client)
    a, b = await _pick_two_item_ids(client, headers=headers)
    f = await _create_draft_fsku(client, headers=headers, name="FSKU-ROLE-GIFT")

    await _replace_components(
        client,
        headers=headers,
        fsku_id=f["id"],
        components=[
            {"item_id": a, "qty": 1, "role": "primary"},
            {"item_id": b, "qty": 1, "role": "gift"},
        ],
    )

    r_get = await client.get(f"/fskus/{f['id']}/components", headers=headers)
    assert r_get.status_code == 200, r_get.text
    body = r_get.json()
    roles = [c.get("role") for c in body.get("components", [])]
    assert "primary" in roles
    assert "gift" in roles


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
async def test_fsku_publish_requires_primary_component(client):
    """
    Phase A 红线：发布前必须至少包含 1 条 role=primary（主销商品）。
    即使 components 非空，但全是 gift，也不允许 publish（409 + Problem shape）。
    """
    headers = await _auth_headers(client)
    item_id = await _pick_any_item_id(client, headers=headers)
    f = await _create_draft_fsku(client, headers=headers, name="FSKU-NO-PRIMARY")

    r_rep = await _post_replace_components(
        client,
        headers=headers,
        fsku_id=f["id"],
        components=[{"item_id": item_id, "qty": 1, "role": "gift"}],
    )
    # replace 在 draft 时允许写入 gift，但必须至少 1 primary：我们选择在 replace 阶段直接 422 拒绝
    assert r_rep.status_code == 422, r_rep.text
    p_rep = r_rep.json()
    _assert_problem_shape(p_rep)
    assert p_rep["http_status"] == 422

    # 再保险：就算未来有人放开 replace，这里也要求 publish 失败（409）
    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 409, r_pub.text
    p = r_pub.json()
    _assert_problem_shape(p)
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
