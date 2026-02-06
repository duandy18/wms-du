# tests/api/test_fskus_contract.py
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
    assert isinstance(token, str) and token
    return {"Authorization": f"Bearer {token}"}


async def _pick_any_item_id(client, headers: Dict[str, str]) -> int:
    r = await client.get("/items", params={"limit": 1}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and data
    return int(data[0]["id"])


async def _create_draft_fsku(
    client,
    headers: Dict[str, str],
    *,
    name: str = "FSKU-TEST",
    shape: str = "bundle",
) -> Dict[str, Any]:
    r = await client.post("/fskus", json={"name": name, "shape": shape}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _replace_components(client, headers: Dict[str, str], fsku_id: int, components: List[dict]):
    r = await client.post(
        f"/fskus/{fsku_id}/components",
        json={"components": components},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_fsku_list_contract_with_archive_fields(client):
    """
    核心合同：
    GET /fskus 必须返回列表页所需的全部字段
    """
    headers = await _auth_headers(client)

    r = await client.get("/fskus", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    assert "items" in data and isinstance(data["items"], list)
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    items = data["items"]
    if not items:
        return

    one = items[0]

    # —— 主键 / 展示字段
    for k in (
        "id",
        "code",
        "name",
        "shape",
        "status",
        "updated_at",
        "components_summary",
        "published_at",
        "retired_at",
    ):
        assert k in one, one

    assert isinstance(one["id"], int)
    assert isinstance(one["code"], str) and one["code"]
    assert isinstance(one["name"], str)
    assert one["shape"] in ("single", "bundle")
    assert one["status"] in ("draft", "published", "retired")
    assert isinstance(one["components_summary"], str)

    # 归档语义必须来自 status/retired_at
    if one["status"] == "retired":
        assert one["retired_at"] is not None
    else:
        assert one["retired_at"] is None


@pytest.mark.asyncio
async def test_fsku_archive_lifecycle(client):
    """
    归档（retire）行为必须在列表中可见
    """
    headers = await _auth_headers(client)
    item_id = await _pick_any_item_id(client, headers)

    f = await _create_draft_fsku(client, headers, name="FSKU-ARCHIVE-TEST")

    await _replace_components(
        client,
        headers,
        fsku_id=f["id"],
        components=[{"item_id": item_id, "qty": 1, "role": "primary"}],
    )

    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200

    r_ret = await client.post(f"/fskus/{f['id']}/retire", headers=headers)
    assert r_ret.status_code == 200
    body = r_ret.json()

    assert body["status"] == "retired"
    assert body["retired_at"] is not None

    # 列表中必须能看到
    r_list = await client.get("/fskus", headers=headers)
    items = r_list.json()["items"]
    hit = next(x for x in items if x["id"] == f["id"])
    assert hit["status"] == "retired"
    assert hit["retired_at"] is not None


@pytest.mark.asyncio
async def test_fsku_unretire_lifecycle(client):
    """
    取消归档（unretire）行为：
    - 仅允许 retired -> published
    - retired_at 必须清空
    - published_at 必须保留历史值（不应被清空）
    - 列表中必须可见
    """
    headers = await _auth_headers(client)
    item_id = await _pick_any_item_id(client, headers)

    f = await _create_draft_fsku(client, headers, name="FSKU-UNRETIRE-TEST")

    await _replace_components(
        client,
        headers,
        fsku_id=f["id"],
        components=[{"item_id": item_id, "qty": 1, "role": "primary"}],
    )

    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200, r_pub.text
    pub = r_pub.json()
    assert pub["status"] == "published"
    assert pub["published_at"] is not None

    r_ret = await client.post(f"/fskus/{f['id']}/retire", headers=headers)
    assert r_ret.status_code == 200, r_ret.text
    ret = r_ret.json()
    assert ret["status"] == "retired"
    assert ret["retired_at"] is not None
    assert ret["published_at"] is not None

    r_un = await client.post(f"/fskus/{f['id']}/unretire", headers=headers)
    assert r_un.status_code == 200, r_un.text
    un = r_un.json()
    assert un["status"] == "published"
    assert un["retired_at"] is None
    assert un["published_at"] is not None

    # 列表中必须能看到恢复结果
    r_list = await client.get("/fskus", headers=headers)
    assert r_list.status_code == 200, r_list.text
    items = r_list.json()["items"]
    hit = next(x for x in items if x["id"] == f["id"])
    assert hit["status"] == "published"
    assert hit["retired_at"] is None


@pytest.mark.asyncio
async def test_fsku_unretire_guard_requires_retired(client):
    """
    护栏：只有 status=retired 才允许 unretire
    - draft -> 409 + Problem
    - published -> 409 + Problem
    """
    headers = await _auth_headers(client)
    item_id = await _pick_any_item_id(client, headers)

    f = await _create_draft_fsku(client, headers, name="FSKU-UNRETIRE-GUARD")

    r_un_draft = await client.post(f"/fskus/{f['id']}/unretire", headers=headers)
    assert r_un_draft.status_code == 409, r_un_draft.text
    _assert_problem_shape(r_un_draft.json())

    await _replace_components(
        client,
        headers,
        fsku_id=f["id"],
        components=[{"item_id": item_id, "qty": 1, "role": "primary"}],
    )

    r_pub = await client.post(f"/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200, r_pub.text

    r_un_pub = await client.post(f"/fskus/{f['id']}/unretire", headers=headers)
    assert r_un_pub.status_code == 409, r_un_pub.text
    _assert_problem_shape(r_un_pub.json())
